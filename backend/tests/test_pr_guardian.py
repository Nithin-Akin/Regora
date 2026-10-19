import json

import pytest

from app.services import pr_guardian


def review_report(status="READY"):
    return {
        "summary": {
            "score": 42,
            "risk": "medium",
            "symbols_changed": 2,
            "affected_files": 3,
            "affected_endpoints": 1,
        },
        "review": {
            "status": status,
            "summary": "Two symbols affect three files.",
            "findings": [],
            "related_tests": ["tests/test_service.py"],
            "changed_test_files": [],
            "coverage_gaps": [],
        },
    }


class Store:
    def __init__(self, policy):
        self.policy = policy
        self.updated = None

    def repository(self, repository_id):
        return {
            "id": repository_id,
            "status": "READY",
            "architecture_policy": json.dumps(self.policy),
        }

    def update_repository(self, repository_id, **updates):
        self.updated = json.loads(updates["last_pr_guardian"])


def test_guardian_runs_pending_then_failure_for_policy(monkeypatch):
    policy = {
        "configured": True,
        "status": "FAIL",
        "rules": [{"status": "FAIL", "name": "Boundary", "violation_count": 1}],
        "error": None,
    }
    store = Store(policy)
    statuses = []
    monkeypatch.setattr(pr_guardian, "get_store", lambda: store)
    pr_guardian.get_store.cache_clear = lambda: None
    monkeypatch.setattr(pr_guardian, "installation_token", lambda installation_id: "token")
    monkeypatch.setattr(
        pr_guardian,
        "fetch_pull_request",
        lambda url, token: {
            "owner": "acme",
            "repository": "shop",
            "pull_request": {"number": 7, "head": {"sha": "abc123"}},
        },
    )
    monkeypatch.setattr(pr_guardian, "intelligence", lambda repository_id: object())
    monkeypatch.setattr(pr_guardian, "analyze_pull_request", lambda *args: review_report())
    monkeypatch.setattr(
        pr_guardian,
        "publish_pull_request_comment",
        lambda *args: {"url": "https://github.com/acme/shop/pull/7#issuecomment-1"},
    )
    monkeypatch.setattr(
        pr_guardian,
        "publish_commit_status",
        lambda owner, repo, sha, state, description, token, target_url="": statuses.append(state),
    )

    result = pr_guardian.review_pull_request(
        "repo-1", "https://github.com/acme/shop/pull/7", 42, "delivery-1", "impact"
    )
    assert statuses == ["pending", "failure"]
    assert result["command"] == "impact"
    assert result["policy_status"] == "FAIL"
    assert store.updated["head_sha"] == "abc123"


def test_guardian_reports_error_status_when_analysis_fails(monkeypatch):
    store = Store({"configured": False, "status": "NOT_CONFIGURED", "rules": [], "error": None})
    statuses = []
    monkeypatch.setattr(pr_guardian, "get_store", lambda: store)
    pr_guardian.get_store.cache_clear = lambda: None
    monkeypatch.setattr(pr_guardian, "installation_token", lambda installation_id: "token")
    monkeypatch.setattr(
        pr_guardian,
        "fetch_pull_request",
        lambda url, token: {
            "owner": "acme",
            "repository": "shop",
            "pull_request": {"number": 7, "head": {"sha": "abc123"}},
        },
    )
    monkeypatch.setattr(pr_guardian, "intelligence", lambda repository_id: object())
    monkeypatch.setattr(
        pr_guardian,
        "analyze_pull_request",
        lambda *args: (_ for _ in ()).throw(RuntimeError("analysis failed")),
    )
    monkeypatch.setattr(
        pr_guardian,
        "publish_commit_status",
        lambda owner, repo, sha, state, description, token, target_url="": statuses.append(state),
    )
    with pytest.raises(RuntimeError, match="analysis failed"):
        pr_guardian.review_pull_request("repo-1", "https://github.com/acme/shop/pull/7", 42)
    assert statuses == ["pending", "error"]


def test_comment_mode_has_bounded_evidence_sections():
    policy = {"configured": False, "status": "NOT_CONFIGURED", "rules": [], "error": None}
    comment = pr_guardian.guardian_comment(review_report(), policy, "explain")
    assert comment.startswith("## Regora Change Explanation")
    assert "Architecture quality gates" in comment
    assert "tests/test_service.py" in comment
