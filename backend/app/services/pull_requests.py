"""Read-only GitHub pull request inspection mapped onto indexed graph evidence."""

import re

import httpx

from app.config import settings


PR_URL = re.compile(
    r"https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)/pull/(?P<number>[1-9][0-9]*)/?"
)
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)


def parse_pull_request_url(url: str) -> tuple[str, str, int]:
    match = PR_URL.fullmatch(url.strip())
    if not match:
        raise ValueError("Use a public GitHub pull request URL: https://github.com/owner/repository/pull/123")
    return match.group("owner"), match.group("repo"), int(match.group("number"))


def repository_identity(url: str) -> tuple[str, str] | None:
    match = re.fullmatch(
        r"https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?",
        url or "",
    )
    return (match.group("owner").lower(), match.group("repo").lower()) if match else None


def validate_pull_request_repository(repository: dict, url: str) -> None:
    owner, repo, _ = parse_pull_request_url(url)
    expected = repository_identity(repository.get("source", ""))
    if repository.get("kind") != "github" or expected != (owner.lower(), repo.lower()):
        raise ValueError("This pull request must belong to the indexed GitHub repository.")


def changed_line_ranges(patch: str) -> list[tuple[int, int]]:
    """Return both base and head hunk ranges because the indexed revision may be either one."""
    ranges = []
    for old_start, old_count, new_start, new_count in HUNK.findall(patch or ""):
        for start, count in ((old_start, old_count or "1"), (new_start, new_count or "1")):
            size = max(1, int(count))
            ranges.append((int(start), int(start) + size - 1))
    return ranges


def fetch_pull_request(url: str) -> dict:
    owner, repo, number = parse_pull_request_url(url)
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Regora",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings().github_token:
        headers["Authorization"] = f"Bearer {settings().github_token}"
    root = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    try:
        with httpx.Client(timeout=20, follow_redirects=False, headers=headers) as client:
            response = client.get(root)
            files_response = client.get(root + "/files", params={"per_page": 100})
    except httpx.HTTPError as exc:
        raise ValueError("GitHub could not be reached. Try again in a moment.") from exc
    if response.status_code == 404:
        raise ValueError("Pull request not found. It must belong to a public repository.")
    if response.status_code == 403 or files_response.status_code == 403:
        raise ValueError("GitHub API limit reached. Set GITHUB_TOKEN in .env and restart Regora.")
    if response.status_code != 200 or files_response.status_code != 200:
        raise ValueError("GitHub could not return this pull request.")
    return {
        "owner": owner,
        "repository": repo,
        "pull_request": response.json(),
        "files": files_response.json(),
        "truncated": 'rel="next"' in files_response.headers.get("link", ""),
    }


def analyze_pull_request(intelligence, repository: dict, payload: dict) -> dict:
    expected = repository_identity(repository.get("source", ""))
    actual = (payload["owner"].lower(), payload["repository"].lower())
    if repository.get("kind") != "github" or expected != actual:
        raise ValueError("This pull request must belong to the indexed GitHub repository.")

    by_file = {}
    for node in intelligence.graph.nodes:
        if node.file_path:
            by_file.setdefault(node.file_path, []).append(node)

    changed_ids = []
    file_results = []
    unmatched = []
    for changed in payload["files"]:
        filename = changed.get("filename", "")
        previous = changed.get("previous_filename", "")
        candidates = by_file.get(filename, []) or by_file.get(previous, [])
        ranges = changed_line_ranges(changed.get("patch", ""))
        symbols = [
            node
            for node in candidates
            if node.type in {"Class", "Interface", "Function", "Method", "Endpoint", "DatabaseEntity"}
            and (not ranges or any(node.start_line <= end and node.end_line >= start for start, end in ranges))
        ]
        if not symbols:
            symbols = [node for node in candidates if node.type == "File"][:1]
        if not symbols:
            unmatched.append(filename)
        for node in symbols:
            if node.id not in changed_ids:
                changed_ids.append(node.id)
        file_results.append(
            {
                "path": filename,
                "status": changed.get("status", "modified"),
                "additions": changed.get("additions", 0),
                "deletions": changed.get("deletions", 0),
                "symbols": [intelligence.public_node(node.id) for node in symbols[:20]],
            }
        )

    impacts = []
    graph_ids = list(changed_ids)
    affected_files = set()
    affected_endpoints = set()
    for symbol_id in changed_ids[:50]:
        impact = intelligence.impact(symbol_id)
        graph_ids.extend(node["id"] for node in impact["graph"]["nodes"])
        affected_files.update(impact["affected_files"])
        affected_endpoints.update(impact["affected_endpoints"])
        impacts.append(
            {
                "node": intelligence.public_node(symbol_id),
                "score": impact["score"],
                "risk": impact["risk"],
                "blast_radius": impact["blast_radius"],
                "affected_files": impact["affected_files"],
                "affected_endpoints": impact["affected_endpoints"],
                "dependency_depth": impact["dependency_depth"],
            }
        )
    impacts.sort(key=lambda item: (item["score"], item["blast_radius"]), reverse=True)
    highest_score = impacts[0]["score"] if impacts else 0
    pr = payload["pull_request"]
    return {
        "pull_request": {
            "number": pr["number"],
            "title": pr["title"],
            "url": pr["html_url"],
            "state": pr["state"],
            "base": pr["base"]["ref"],
            "head": pr["head"]["ref"],
        },
        "summary": {
            "files_changed": len(file_results),
            "symbols_changed": len(changed_ids),
            "affected_files": len(affected_files),
            "affected_endpoints": len(affected_endpoints),
            "score": highest_score,
            "risk": "HIGH" if highest_score >= 65 else "MEDIUM" if highest_score >= 30 else "LOW",
        },
        "files": file_results,
        "impacts": impacts[:20],
        "unmatched_files": unmatched,
        "graph": intelligence.subgraph(graph_ids, limit=300),
        "truncated": payload["truncated"] or len(changed_ids) > 50,
        "caveat": "Potential impact is calculated from the currently indexed revision and static dependencies. Added files and dynamic behavior may require reindexing the pull request branch.",
    }
