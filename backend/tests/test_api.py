import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.graph.store import get_store
from app.api.routes import ready


class FakeStore:
    def repositories(self):
        return [{"id": "r", "name": "Test", "status": "READY", "source_root": "private", "logs": "[]"}]

    def repository(self, id):
        return {"id": "r", "name": "Test", "status": "READY", "warnings": "[]"} if id == "r" else None


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
