from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api import routes
from app.graph.store import get_store
from app.main import app
from app.security.auth import CurrentUser, current_user


class IntegrationStore:
    def __init__(self):
        self.repository_data = {
            "id": "repo-1",
            "name": "shop",
            "kind": "github",
            "source": "https://github.com/acme/shop",
            "status": "READY",
            "owner_id": "local",
            "github_installation_id": 42,
        }
        self.runs = {
            "failed-1": {
                "id": "failed-1",
                "repository_id": "repo-1",
                "status": "ERROR",
                "pull_request": 7,
                "pr_url": "https://github.com/acme/shop/pull/7",
                "head_sha": "abc123",
                "command": "review",
                "installation_id": 42,
                "created_at": "2026-10-25T08:00:00+00:00",
                "error": "analysis failed",
            }
        }

    def repository(self, id, owner_id=None):
        if id != "repo-1" or owner_id not in {None, "local"}:
            return None
        return self.repository_data

    def guardian_runs(self, repository_id, limit=50):
        return list(self.runs.values())[:limit]

    def guardian_run(self, id, repository_id):
        run = self.runs.get(id)
        return run if run and run["repository_id"] == repository_id else None

    def create_guardian_retry(self, source, data):
        return self.runs.setdefault(data["id"], data)

    def update_guardian_run(self, id, **fields):
        self.runs[id].update(fields)


def configured_settings():
    return SimpleNamespace(
        github_app_id="123",
        github_app_private_key="private-key",
        github_webhook_secret="webhook-secret",
        github_token="",
    )


def test_integration_health_and_history_are_owner_scoped(monkeypatch):
    store = IntegrationStore()
    monkeypatch.setattr(routes, "settings", configured_settings)
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)

    response = client.get("/api/repositories/repo-1/github-integration")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "READY"
    assert result["authentication"] == "GITHUB_APP"
    assert result["repository"] == {
        "github_repository": True,
        "bound": True,
        "installation_id": 42,
    }
    assert result["runs"][0]["error"] == "analysis failed"
    assert "github_app_private_key" not in str(result)

    app.dependency_overrides[current_user] = lambda: CurrentUser("github:other")
    assert client.get("/api/repositories/repo-1/github-integration").status_code == 404
    app.dependency_overrides.clear()


def test_failed_review_retry_is_idempotently_enqueued(monkeypatch):
    store = IntegrationStore()
    enqueued = []

    class Queue:
        def __init__(self, name, connection):
            assert name == "pull-requests"

        def enqueue(self, function, *args, **kwargs):
            enqueued.append((function, args, kwargs))
            return SimpleNamespace(id="job-1")

    monkeypatch.setattr(routes, "Queue", Queue)
    monkeypatch.setattr(routes, "redis_connection", lambda: object())
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)

    first = client.post("/api/repositories/repo-1/github-integration/runs/failed-1/retry")
    second = client.post("/api/repositories/repo-1/github-integration/runs/failed-1/retry")
    app.dependency_overrides.clear()

    assert first.status_code == 202
    assert first.json()["status"] == "queued"
    assert second.status_code == 202
    assert second.json()["status"] == "duplicate"
    assert len(enqueued) == 1
    assert enqueued[0][1][-1] == "retry:failed-1"
    assert enqueued[0][2]["on_failure"] is routes.guardian_job_failure


def test_only_failed_reviews_can_be_retried():
    store = IntegrationStore()
    store.runs["failed-1"]["status"] = "COMPLETE"
    app.dependency_overrides[get_store] = lambda: store
    response = TestClient(app).post(
        "/api/repositories/repo-1/github-integration/runs/failed-1/retry"
    )
    app.dependency_overrides.clear()
    assert response.status_code == 409
