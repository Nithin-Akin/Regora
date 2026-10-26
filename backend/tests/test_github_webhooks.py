from fastapi.testclient import TestClient

from app.api import github_webhooks
from app.graph.store import get_store
from app.main import app


class Redis:
    def __init__(self):
        self.keys = set()

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return False
        self.keys.add(key)
        return True

    def delete(self, key):
        self.keys.discard(key)


class Store:
    def __init__(self):
        self.updated = None
        self.runs = []

    def github_repository(self, owner, name, installation_id):
        assert (owner, name, installation_id) == ("acme", "shop", 42)
        return {"status": "BOUND", "repository": {"id": "repo-1", "github_installation_id": 42}}

    def update_repository(self, repository_id, **updates):
        self.updated = (repository_id, updates)

    def create_guardian_run(self, data):
        self.runs.append(data)
        return data

    def update_guardian_run(self, run_id, **updates):
        self.updated = (run_id, updates)


def pull_request_payload():
    return {
        "action": "synchronize",
        "repository": {"full_name": "acme/shop"},
        "installation": {"id": 42},
        "pull_request": {
            "draft": False,
            "html_url": "https://github.com/acme/shop/pull/7",
            "head": {"sha": "abc123"},
        },
    }


def test_pull_request_event_is_deduplicated_and_queued(monkeypatch):
    cache = Redis()
    store = Store()
    captured = {}

    class Queue:
        def __init__(self, name, connection):
            assert name == "pull-requests"
            assert connection is cache

        def enqueue(self, function, *args, **kwargs):
            captured.update(function=function, args=args, kwargs=kwargs)
            return type("Job", (), {"id": "job-1"})()

    monkeypatch.setattr(github_webhooks, "verify_webhook_signature", lambda body, signature: None)
    monkeypatch.setattr(github_webhooks, "redis_connection", lambda: cache)
    monkeypatch.setattr(github_webhooks, "Queue", Queue)
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)
    headers = {
        "X-Hub-Signature-256": "signed",
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "delivery-1",
    }
    first = client.post("/api/github/webhooks", json=pull_request_payload(), headers=headers)
    second = client.post("/api/github/webhooks", json=pull_request_payload(), headers=headers)
    app.dependency_overrides.clear()

    assert first.status_code == 202
    assert first.json()["status"] == "queued"
    assert second.json()["status"] == "duplicate"
    assert captured["args"][:6] == (
        "repo-1",
        "https://github.com/acme/shop/pull/7",
        42,
        "delivery-1",
        "review",
        "abc123",
    )
    assert captured["args"][6] == store.runs[0]["id"]
    assert store.runs[0]["status"] == "QUEUED"
    assert store.runs[0]["pr_url"] == "https://github.com/acme/shop/pull/7"
    assert store.updated is None


def test_only_trusted_pull_request_commands_are_selected():
    payload = {
        "action": "created",
        "issue": {"pull_request": {"html_url": "https://github.com/acme/shop/pull/7"}},
        "comment": {"body": "/regora impact", "author_association": "COLLABORATOR"},
    }
    assert github_webhooks.selected_pull_request("issue_comment", payload) == (
        "https://github.com/acme/shop/pull/7",
        "impact",
    )
    payload["comment"]["author_association"] = "NONE"
    assert github_webhooks.selected_pull_request("issue_comment", payload) is None


def test_invalid_webhook_signature_is_rejected(monkeypatch):
    monkeypatch.setattr(
        github_webhooks,
        "verify_webhook_signature",
        lambda body, signature: (_ for _ in ()).throw(ValueError("Invalid GitHub webhook signature")),
    )
    response = TestClient(app).post(
        "/api/github/webhooks",
        content=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "ping",
            "X-GitHub-Delivery": "delivery-2",
        },
    )
    assert response.status_code == 401


def test_repository_failure_releases_delivery_for_github_retry(monkeypatch):
    cache = Redis()

    class FailingStore(Store):
        def github_repository(self, owner, name, installation_id):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(github_webhooks, "verify_webhook_signature", lambda body, signature: None)
    monkeypatch.setattr(github_webhooks, "redis_connection", lambda: cache)
    app.dependency_overrides[get_store] = lambda: FailingStore()
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/github/webhooks",
        json=pull_request_payload(),
        headers={
            "X-Hub-Signature-256": "signed",
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "delivery-retry",
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 500
    assert "regora:github-delivery:delivery-retry" not in cache.keys


def test_ambiguous_repository_binding_is_reported_without_queueing(monkeypatch):
    cache = Redis()

    class AmbiguousStore(Store):
        def github_repository(self, owner, name, installation_id):
            return {"status": "AMBIGUOUS", "repository": None}

    monkeypatch.setattr(github_webhooks, "verify_webhook_signature", lambda body, signature: None)
    monkeypatch.setattr(github_webhooks, "redis_connection", lambda: cache)
    app.dependency_overrides[get_store] = lambda: AmbiguousStore()
    response = TestClient(app).post(
        "/api/github/webhooks",
        json=pull_request_payload(),
        headers={
            "X-Hub-Signature-256": "signed",
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "delivery-ambiguous",
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["status"] == "ignored"
    assert response.json()["reason"] == "ambiguous_repository_binding"
    assert "regora:github-delivery:delivery-ambiguous" not in cache.keys


def test_binding_failure_allows_same_github_delivery_to_be_redelivered(monkeypatch):
    cache = Redis()
    store = Store()
    attempts = 0

    def github_repository(owner, name, installation_id):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return {"status": "NOT_FOUND", "repository": None}
        return {"status": "BOUND", "repository": {"id": "repo-1", "github_installation_id": 42}}

    class Queue:
        def __init__(self, name, connection):
            pass

        def enqueue(self, function, *args, **kwargs):
            return type("Job", (), {"id": "job-redelivery"})()

    store.github_repository = github_repository
    monkeypatch.setattr(github_webhooks, "verify_webhook_signature", lambda body, signature: None)
    monkeypatch.setattr(github_webhooks, "redis_connection", lambda: cache)
    monkeypatch.setattr(github_webhooks, "Queue", Queue)
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)
    headers = {
        "X-Hub-Signature-256": "signed",
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "delivery-redelivered",
    }

    first = client.post("/api/github/webhooks", json=pull_request_payload(), headers=headers)
    second = client.post("/api/github/webhooks", json=pull_request_payload(), headers=headers)
    app.dependency_overrides.clear()

    assert first.json() == {
        "status": "ignored",
        "reason": "repository_not_indexed",
        "delivery_id": "delivery-redelivered",
    }
    assert second.json()["status"] == "queued"
    assert attempts == 2
