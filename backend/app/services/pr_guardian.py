"""Continuous, evidence-backed pull-request review workflow."""

import json
import logging
from datetime import UTC, datetime

from app.graph.store import get_store
from app.services.architecture_policy import empty_policy
from app.services.cache import intelligence
from app.services.github_app import installation_token, publish_commit_status
from app.services.pull_requests import analyze_pull_request, fetch_pull_request, publish_pull_request_comment

log = logging.getLogger("regora.pr_guardian")


def _failure_message(exc: Exception) -> str:
    if isinstance(exc, (RuntimeError, ValueError)):
        return str(exc)[:300]
    return f"{type(exc).__name__}: automatic review failed"


def guardian_comment(report: dict, policy: dict, command: str = "review") -> str:
    summary = report["summary"]
    review = report["review"]
    policy_status = policy["status"]
    attention = review["status"] == "ATTENTION" or policy_status in {"FAIL", "INVALID"}
    title = {
        "review": "PR Guardian Review",
        "impact": "Change Impact Analysis",
        "explain": "Change Explanation",
    }.get(command, "PR Guardian Review")
    lines = [
        f"## Regora {title}",
        "",
        f"**{'Attention required' if attention else 'Review ready'}** · Risk **{summary['score']}/100 ({summary['risk']})**",
        "",
        review["summary"],
        "",
        "| Changed symbols | Affected files | API routes | Architecture policy |",
        "| ---: | ---: | ---: | --- |",
        f"| {summary['symbols_changed']} | {summary['affected_files']} | {summary['affected_endpoints']} | {policy_status} |",
        "",
        "### Findings",
        "",
    ]
    if review["findings"]:
        for finding in review["findings"][:8]:
            lines.append(
                f"- **{finding['severity'].upper()} · {finding['title']}** — {finding['detail']} "
                f"(`{finding['file']}:{finding['start_line']}`)"
            )
    else:
        lines.append("- No mapped impact findings.")
    lines.extend(["", "### Architecture quality gates", ""])
    if policy["configured"]:
        if policy.get("error"):
            lines.append(f"- **INVALID** — {policy['error']}")
        for rule in policy["rules"]:
            lines.append(f"- **{rule['status']} · {rule['name']}** — {rule['violation_count']} violations")
    else:
        lines.append("- No `.regora.yml` policy is configured.")
    lines.extend(["", "### Test signals", ""])
    tests = sorted(set(review["related_tests"] + review["changed_test_files"]))
    lines.extend([f"- `{path}`" for path in tests[:20]] or ["- No connected or changed test files were identified."])
    if review["coverage_gaps"]:
        lines.extend(["", f"**Coverage gaps:** {len(review['coverage_gaps'])} changed symbols lack a connected test."])
    lines.extend(
        [
            "",
            "> Static analysis uses the currently indexed revision. Added files and dynamic runtime behavior may require reindexing.",
        ]
    )
    return "\n".join(lines)[:59000]


def review_pull_request(
    repository_id: str,
    pr_url: str,
    installation_id: int,
    delivery_id: str = "",
    command: str = "review",
    head_sha: str = "",
) -> dict:
    get_store.cache_clear()
    store = get_store()
    repository = store.repository(repository_id)
    if not repository or repository.get("status") != "READY":
        raise ValueError("The indexed repository is not ready for automatic review")
    token = ""
    payload = None
    try:
        token = installation_token(installation_id)
        payload = fetch_pull_request(pr_url, token)
        pr = payload["pull_request"]
        head_sha = pr["head"]["sha"]
        publish_commit_status(
            payload["owner"],
            payload["repository"],
            head_sha,
            "pending",
            "Analyzing change impact",
            token,
        )
        report = analyze_pull_request(intelligence(repository_id), repository, payload)
        policy = (
            json.loads(repository["architecture_policy"])
            if repository.get("architecture_policy")
            else empty_policy()
        )
        comment = guardian_comment(report, policy, command)
        publication = publish_pull_request_comment(pr_url, comment, token, f"app:{installation_id}")
        policy_failed = policy["status"] in {"FAIL", "INVALID"}
        attention = report["review"]["status"] == "ATTENTION"
        publish_commit_status(
            payload["owner"],
            payload["repository"],
            head_sha,
            "failure" if policy_failed else "success",
            "Architecture policy failed"
            if policy_failed
            else "Review complete with attention items"
            if attention
            else "Review complete",
            token,
            publication["url"],
        )
        result = {
            "status": "COMPLETE",
            "delivery_id": delivery_id,
            "pull_request": pr["number"],
            "head_sha": head_sha,
            "review_status": report["review"]["status"],
            "policy_status": policy["status"],
            "command": command,
            "comment": publication,
        }
        store.update_repository(repository_id, last_pr_guardian=json.dumps(result))
        log.info(json.dumps({"repository_id": repository_id, **result}))
        return result
    except Exception as exc:
        if token and head_sha:
            try:
                owner, name = (
                    (payload["owner"], payload["repository"])
                    if payload
                    else pr_url.removeprefix("https://github.com/").split("/", 2)[:2]
                )
                publish_commit_status(
                    owner,
                    name,
                    head_sha,
                    "error",
                    "Automatic review failed",
                    token,
                )
            except Exception:
                log.exception("Unable to publish the failed guardian status")
        failure = {
            "status": "ERROR",
            "delivery_id": delivery_id,
            "head_sha": head_sha,
            "command": command,
            "error": _failure_message(exc),
            "failed_at": datetime.now(UTC).isoformat(),
        }
        try:
            store.update_repository(repository_id, last_pr_guardian=json.dumps(failure))
        except Exception:
            log.exception("Unable to persist the failed guardian run")
        log.error(json.dumps({"repository_id": repository_id, **failure}))
        raise
