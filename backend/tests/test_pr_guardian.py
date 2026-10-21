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
            "kind": "github",
            "source": "https://github.com/acme/shop",
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
    monkeypatch.setattr(
        pr_guardian,
        "analyze_pull_request_head",
        lambda *args: (review_report(), policy),
    )
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
    monkeypatch.setattr(
        pr_guardian,
        "analyze_pull_request_head",
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
    assert store.updated["status"] == "ERROR"
    assert store.updated["error"] == "analysis failed"


def test_guardian_persists_installation_authentication_failure(monkeypatch):
    store = Store({"configured": False, "status": "NOT_CONFIGURED", "rules": [], "error": None})
    monkeypatch.setattr(pr_guardian, "get_store", lambda: store)
    pr_guardian.get_store.cache_clear = lambda: None
    monkeypatch.setattr(
        pr_guardian,
        "installation_token",
        lambda installation_id: (_ for _ in ()).throw(RuntimeError("GitHub App authentication failed")),
    )

    with pytest.raises(RuntimeError, match="authentication failed"):
        pr_guardian.review_pull_request(
            "repo-1",
            "https://github.com/acme/shop/pull/7",
            42,
            "delivery-auth",
            head_sha="abc123",
        )
    assert store.updated["status"] == "ERROR"
    assert store.updated["head_sha"] == "abc123"
    assert store.updated["error"] == "GitHub App authentication failed"


def test_guardian_marks_known_head_when_pull_request_fetch_fails(monkeypatch):
    store = Store({"configured": False, "status": "NOT_CONFIGURED", "rules": [], "error": None})
    statuses = []
    monkeypatch.setattr(pr_guardian, "get_store", lambda: store)
    pr_guardian.get_store.cache_clear = lambda: None
    monkeypatch.setattr(pr_guardian, "installation_token", lambda installation_id: "token")
    monkeypatch.setattr(
        pr_guardian,
        "fetch_pull_request",
        lambda url, token: (_ for _ in ()).throw(ValueError("GitHub could not return this pull request.")),
    )
    monkeypatch.setattr(
        pr_guardian,
        "publish_commit_status",
        lambda owner, repo, sha, state, description, token, target_url="": statuses.append(state),
    )

    with pytest.raises(ValueError, match="could not return"):
        pr_guardian.review_pull_request(
            "repo-1",
            "https://github.com/acme/shop/pull/7",
            42,
            "delivery-fetch",
            head_sha="abc123",
        )
    assert statuses == ["error"]
    assert store.updated["status"] == "ERROR"
    assert store.updated["error"] == "GitHub could not return this pull request."


def test_comment_mode_has_bounded_evidence_sections():
    policy = {"configured": False, "status": "NOT_CONFIGURED", "rules": [], "error": None}
    comment = pr_guardian.guardian_comment(review_report(), policy, "explain")
    assert comment.startswith("## Regora Change Explanation")
    assert "Architecture quality gates" in comment
    assert "tests/test_service.py" in comment


def test_pull_request_head_introduced_policy_violation_fails(tmp_path, monkeypatch):
    def clone(url, destination, pull_request, token):
        destination.mkdir()
        (destination / "api").mkdir()
        (destination / "data").mkdir()
        (destination / "api/routes.py").write_text(
            "from data.store import save\n\ndef checkout():\n    save()\n"
        )
        (destination / "data/store.py").write_text("def save():\n    return True\n")
        (destination / ".regora.yml").write_text(
            "version: 1\n"
            "rules:\n"
            "  - id: api-data\n"
            "    type: forbid_dependency\n"
            "    name: API cannot call data directly\n"
            "    from: api/**\n"
            "    to: data/**\n"
            "    relationships: [CALLS]\n"
            "    severity: error\n"
        )
        return destination

    monkeypatch.setattr(pr_guardian, "clone_github_pull", clone)
    payload = {
        "owner": "acme",
        "repository": "shop",
        "pull_request": {
            "number": 7,
            "title": "Break the API boundary",
            "html_url": "https://github.com/acme/shop/pull/7",
            "state": "open",
            "base": {"ref": "main"},
            "head": {"ref": "boundary-change", "sha": "abc123"},
        },
        "files": [
            {
                "filename": "api/routes.py",
                "status": "modified",
                "additions": 4,
                "deletions": 0,
                "patch": "@@ -1,0 +1,4 @@",
            }
        ],
        "truncated": False,
    }
    report, policy = pr_guardian.analyze_pull_request_head(
        "repo-1",
        {"kind": "github", "source": "https://github.com/acme/shop"},
        payload,
        "token",
    )
    assert report["analysis_revision"] == "pull-request-head"
    assert report["summary"]["symbols_changed"] >= 1
    assert policy["status"] == "FAIL"
    assert policy["violations"][0]["rule_id"] == "api-data"
