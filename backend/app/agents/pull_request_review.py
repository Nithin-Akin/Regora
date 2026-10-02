"""Deterministic review agent over pull-request and graph evidence."""

from pathlib import PurePosixPath


def is_test_path(path: str) -> bool:
    parts = [part.lower() for part in PurePosixPath(path).parts]
    name = parts[-1] if parts else ""
    return (
        any(part in {"test", "tests", "__tests__", "spec", "specs"} for part in parts[:-1])
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.js", ".test.jsx", ".test.ts", ".test.tsx"))
        or name.endswith((".spec.js", ".spec.jsx", ".spec.ts", ".spec.tsx"))
    )


class PullRequestReviewAgent:
    """Turn bounded static-analysis results into a review-ready evidence contract."""

    def __init__(self, intelligence):
        self.intelligence = intelligence

    def related_tests(self, impact: dict) -> list[str]:
        return sorted(
            {
                node.get("file_path", "")
                for node in impact.get("graph", {}).get("nodes", [])
                if node.get("file_path") and is_test_path(node["file_path"])
            }
        )

    def review(self, result: dict) -> dict:
        impacts = result["impacts"]
        related_tests = sorted({path for item in impacts for path in item["related_tests"]})
        changed_test_files = sorted(file["path"] for file in result["files"] if is_test_path(file["path"]))
        coverage_gaps = [
            {
                "symbol_id": item["node"]["id"],
                "symbol": item["node"]["name"],
                "file": item["node"]["file_path"],
                "start_line": item["node"]["start_line"],
                "end_line": item["node"]["end_line"],
                "risk": item["risk"],
                "reason": "No statically connected test file was found in the indexed graph.",
            }
            for item in impacts
            if not is_test_path(item["node"]["file_path"]) and not item["related_tests"]
        ]
        findings = [
            {
                "id": f"impact:{item['node']['id']}",
                "severity": item["risk"].lower(),
                "title": f"{item['node']['name']} has {item['risk'].lower()} structural impact",
                "detail": (
                    f"{item['blast_radius']} dependent symbols across {len(item['affected_files'])} files; "
                    f"{len(item['affected_endpoints'])} API routes are reachable from the affected graph."
                ),
                "symbol_id": item["node"]["id"],
                "file": item["node"]["file_path"],
                "start_line": item["node"]["start_line"],
                "end_line": item["node"]["end_line"],
                "related_tests": item["related_tests"],
            }
            for item in impacts[:8]
        ]
        checklist = [
            {
                "id": "mapped-files",
                "label": "Inspect every changed file",
                "status": "warning" if result["unmatched_files"] else "pass",
                "detail": (
                    f"{len(result['unmatched_files'])} changed files could not be mapped to indexed symbols."
                    if result["unmatched_files"]
                    else "Every changed file was mapped to indexed graph evidence."
                ),
            },
            {
                "id": "related-tests",
                "label": "Run related tests",
                "status": "pass" if related_tests or changed_test_files else "warning",
                "detail": (
                    f"Review {len(set(related_tests + changed_test_files))} connected or changed test files."
                    if related_tests or changed_test_files
                    else "No connected or changed test file was identified by static analysis."
                ),
            },
            {
                "id": "coverage-signals",
                "label": "Review test coverage signals",
                "status": "warning" if coverage_gaps else "pass",
                "detail": (
                    f"{len(coverage_gaps)} changed symbols have no statically connected test file."
                    if coverage_gaps
                    else "Every mapped changed symbol has a statically connected test file."
                ),
            },
            {
                "id": "high-impact",
                "label": "Inspect high-impact changes",
                "status": "warning" if any(item["risk"] == "HIGH" for item in impacts) else "pass",
                "detail": (
                    "At least one changed symbol has high structural impact."
                    if any(item["risk"] == "HIGH" for item in impacts)
                    else "No changed symbol reached the high structural-impact threshold."
                ),
            },
        ]
        if result["truncated"]:
            checklist.append(
                {
                    "id": "truncated",
                    "label": "Inspect analysis limits",
                    "status": "warning",
                    "detail": "The pull-request evidence exceeded a configured analysis limit.",
                }
            )
        highest = impacts[0]["node"]["name"] if impacts else "the changed files"
        needs_attention = bool(
            coverage_gaps
            or result["unmatched_files"]
            or result["truncated"]
            or any(item["risk"] == "HIGH" for item in impacts)
        )
        return {
            "status": "ATTENTION" if needs_attention else "REVIEW",
            "headline": f"Review {highest} before merging",
            "summary": (
                f"Regora mapped {result['summary']['symbols_changed']} changed symbols and "
                f"{len(related_tests)} statically connected test files."
            ),
            "related_tests": related_tests,
            "changed_test_files": changed_test_files,
            "coverage_gaps": coverage_gaps,
            "findings": findings,
            "checklist": checklist,
            "grounding": "static-evidence",
        }
