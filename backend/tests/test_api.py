import json

import pytest
from fastapi.testclient import TestClient

import app.api.routes as routes
from app.api.routes import ready
from app.graph.store import get_store
from app.main import app
from app.models.schema import Answer


class FakeStore:
    def repositories(self):
        return [{"id": "r", "name": "Test", "status": "READY", "source_root": "private", "logs": "[]"}]

    def repository(self, id):
        return (
            {
                "id": "r",
                "name": "Test",
                "status": "READY",
                "warnings": "[]",
                "kind": "github",
                "source": "https://github.com/acme/shop",
            }
            if id == "r"
            else None
        )


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


def test_invalid_github_is_rejected_before_queue(client):
    response = client.post("/api/repositories/github", json={"url": "https://evil.test/repo"})
    assert response.status_code == 422


def test_source_only_serves_indexed_files(client):
    assert client.get("/api/repositories/r/source", params={"path": "../../etc/passwd"}).status_code == 404
    data = client.get("/api/repositories/r/source", params={"path": "utils/tokens.py"}).json()
    assert "def verify_token" in data["source"]


def test_graph_overview_search_and_limits(client):
    assert client.get("/api/repositories/r/overview").json()["files"] > 0
    assert client.get("/api/repositories/r/graph").json()["nodes"]
    assert client.get("/api/repositories/r/graph?depth=50").status_code == 422
    response = client.get("/api/repositories/r/search?q=verify_token&mode=symbol")
    assert response.json()["results"][0]["name"] == "verify_token"


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
        lambda url: {
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
