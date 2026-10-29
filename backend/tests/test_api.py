import json

import pytest
from fastapi.testclient import TestClient

import app.api.routes as routes
from app.api.routes import ready
from app.graph.store import get_store
from app.main import app
from app.models.schema import Answer, CodeGraph, CodeNode
from app.security.auth import CurrentUser, current_user


class FakeStore:
    def repositories(self, owner_id=None):
        return (
            [
                {
                    "id": "r",
                    "name": "Test",
                    "status": "READY",
                    "source_root": "private",
                    "owner_id": "local",
                    "logs": "[]",
                }
            ]
            if owner_id == "local"
            else []
        )

    def repository(self, id, owner_id=None):
        return (
            {
                "id": "r",
                "name": "Test",
                "status": "READY",
                "warnings": "[]",
                "architecture_policy": json.dumps(
                    {
                        "configured": True,
                        "source": ".regora.yml",
                        "status": "PASS",
                        "summary": {"rules": 1, "passed": 1, "warnings": 0, "errors": 0, "violations": 0},
                        "rules": [],
                        "violations": [],
                        "error": None,
                    }
                ),
                "kind": "github",
                "source": "https://github.com/acme/shop",
            }
            if id == "r" and owner_id in {None, "local"}
            else None
        )

    def graph_snapshots(self, repository_id, limit=20):
        return [
            {
                "id": "snapshot-1",
                "repository_id": repository_id,
                "commit_sha": "a" * 40,
                "fingerprint": "fingerprint-1",
                "nodes": 10,
                "relationships": 20,
                "created_at": "2026-10-29T00:00:00Z",
                "trigger": "push",
                "format": "zlib-json-v1",
            }
        ][:limit]

    def graph_snapshot(self, repository_id, commit_sha):
        if commit_sha not in {"a" * 40, "b" * 40}:
            return None
        return {
            **self.graph_snapshots(repository_id)[0],
            "commit_sha": commit_sha,
            "graph": CodeGraph(
                nodes=[
                    CodeNode(
                        id="symbol",
                        name="symbol",
                        type="Function",
                        repository_id=repository_id,
                        hash="old" if commit_sha.startswith("a") else "new",
                    )
                ]
            ),
        }


@pytest.fixture
def client(demo_intelligence):
    app.dependency_overrides[get_store] = lambda: FakeStore()
    app.dependency_overrides[ready] = lambda: demo_intelligence
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_repository_metadata_hides_filesystem(client):
    response = client.get("/api/repositories")
    assert response.status_code == 200
    assert "source_root" not in response.json()[0]
    assert "owner_id" not in response.json()[0]


def test_repository_access_is_scoped_to_owner(client):
    app.dependency_overrides[current_user] = lambda: CurrentUser("github:99")
    assert client.get("/api/repositories").json() == []
    assert client.get("/api/repositories/r/status").status_code == 404
    assert client.get("/api/repositories/r/versions").status_code == 404


def test_repository_versions_return_metadata_without_graph_payload(client):
    response = client.get("/api/repositories/r/versions")
    assert response.status_code == 200
    version = response.json()["versions"][0]
    assert version["commit_sha"] == "a" * 40
    assert version["nodes"] == 10
    assert "payload" not in version


def test_repository_versions_can_be_compared(client):
    response = client.get(
        "/api/repositories/r/versions/compare",
        params={"base_sha": "a" * 40, "head_sha": "b" * 40},
    )
    assert response.status_code == 200
    assert response.json()["summary"]["symbols"]["modified"] == 1
    assert "graph" not in response.json()["base"]


def test_repository_version_comparison_validates_commits(client):
    assert (
        client.get(
            "/api/repositories/r/versions/compare",
            params={"base_sha": "bad", "head_sha": "b" * 40},
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/repositories/r/versions/compare",
            params={"base_sha": "c" * 40, "head_sha": "b" * 40},
        ).status_code
        == 404
    )


def test_invalid_github_is_rejected_before_queue(client):
    response = client.post("/api/repositories/github", json={"url": "https://evil.test/repo"})
    assert response.status_code == 422


def test_demo_reuses_existing_workspace(client):
    class DemoStore(FakeStore):
        def repositories(self, owner_id=None):
            return [
                {
                    "id": "demo-ready",
                    "name": "Northstar Commerce",
                    "kind": "demo",
                    "source": "included-demo",
                    "status": "READY",
                    "owner_id": owner_id,
                    "logs": "[]",
                }
            ]

    app.dependency_overrides[get_store] = lambda: DemoStore()
    response = client.post("/api/repositories/demo")
    assert response.status_code == 202
    assert response.json()["id"] == "demo-ready"
    assert "owner_id" not in response.json()


def test_source_only_serves_indexed_files(client):
    assert client.get("/api/repositories/r/source", params={"path": "../../etc/passwd"}).status_code == 404
    data = client.get("/api/repositories/r/source", params={"path": "utils/tokens.py"}).json()
    assert "def verify_token" in data["source"]


def test_graph_overview_search_and_limits(client):
    overview = client.get("/api/repositories/r/overview").json()
    assert overview["files"] > 0
    assert overview["architecture_policy"]["status"] == "PASS"
    assert client.get("/api/repositories/r/architecture-policy").json()["source"] == ".regora.yml"
    assert client.get("/api/repositories/r/architecture-policy/check").status_code == 200
    assert client.get("/api/repositories/r/graph").json()["nodes"]
    assert client.get("/api/repositories/r/graph?depth=50").status_code == 422
    response = client.get("/api/repositories/r/search?q=verify_token&mode=symbol")
    assert response.json()["results"][0]["name"] == "verify_token"


def test_architecture_policy_check_fails_for_error_violations(client):
    class FailingPolicyStore(FakeStore):
        def repository(self, id, owner_id=None):
            repository = super().repository(id, owner_id)
            if repository:
                repository["architecture_policy"] = json.dumps(
                    {
                        "configured": True,
                        "source": ".regora.yml",
                        "status": "FAIL",
                        "summary": {"rules": 1, "passed": 0, "warnings": 0, "errors": 1, "violations": 1},
                        "rules": [],
                        "violations": [],
                        "error": None,
                    }
                )
            return repository

    app.dependency_overrides[get_store] = lambda: FailingPolicyStore()
    response = client.get("/api/repositories/r/architecture-policy/check")
    assert response.status_code == 409
    assert response.json()["detail"]["policy"]["status"] == "FAIL"


def test_unknown_symbol_returns_404(client):
    assert client.get("/api/repositories/r/symbols/missing").status_code == 404
    assert client.post("/api/repositories/r/trace", json={"source_id": "missing"}).status_code == 404


def test_invalid_zip_rejected(client):
    response = client.post("/api/repositories/upload", files={"file": ("bad.zip", b"not a zip", "application/zip")})
    assert response.status_code == 422


def test_pull_request_impact_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        routes,
        "fetch_pull_request",
        lambda url, token="": {
            "owner": "acme",
            "repository": "shop",
            "pull_request": {
                "number": 12,
                "title": "Change authentication",
                "html_url": url,
                "state": "open",
                "base": {"ref": "main"},
                "head": {"ref": "auth-change"},
            },
            "files": [
                {
                    "filename": "services/auth.py",
                    "status": "modified",
                    "additions": 1,
                    "deletions": 1,
                    "patch": "@@ -4,6 +4,6 @@",
                }
            ],
            "truncated": False,
        },
    )
    response = client.post(
        "/api/repositories/r/pull-request-impact",
        json={"url": "https://github.com/acme/shop/pull/12"},
    )
    assert response.status_code == 200
    assert response.json()["summary"]["symbols_changed"] >= 1


def test_publish_pull_request_review_endpoint(client, monkeypatch):
    app.dependency_overrides[current_user] = lambda: CurrentUser("local", "github-token")
    monkeypatch.setattr(
        routes,
        "publish_pull_request_comment",
        lambda url, comment, token, actor_id: {
            "id": 91,
            "url": "https://github.com/acme/shop/pull/12#issuecomment-91",
            "created_at": "2026-10-04T10:00:00Z",
            "action": "created",
        },
    )
    response = client.post(
        "/api/repositories/r/pull-request-review/comment",
        json={
            "url": "https://github.com/acme/shop/pull/12",
            "comment": "## Regora review\nGrounded evidence.",
        },
    )
    assert response.status_code == 201
    assert response.json()["action"] == "created"


def test_publish_pull_request_review_rejects_other_repository(client):
    response = client.post(
        "/api/repositories/r/pull-request-review/comment",
        json={
            "url": "https://github.com/other/project/pull/12",
            "comment": "Review",
        },
    )
    assert response.status_code == 422


def test_assistant_stream_reports_progress_and_validated_result(client, monkeypatch):
    class StreamingAgent:
        def __init__(self, *args):
            pass

        def ask(self, request, progress=None):
            progress("Searching the code graph")
            progress("Validating citations")
            return Answer(
                answer="Grounded streamed answer.",
                confidence=0.8,
                grounding="static-evidence",
                session_id="stream-session",
            )

    monkeypatch.setattr(routes, "RepoAgent", StreamingAgent)
    response = client.post(
        "/api/repositories/r/ask/stream",
        json={"question": "Explain authentication"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["message"] for event in events if event["type"] == "status"] == [
        "Searching the code graph",
        "Validating citations",
    ]
    assert "".join(event["text"] for event in events if event["type"] == "delta") == "Grounded streamed answer."
    assert events[-1]["type"] == "result"
    assert events[-1]["answer"]["session_id"] == "stream-session"
