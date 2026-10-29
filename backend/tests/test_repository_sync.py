from types import SimpleNamespace

from app.services import repository_sync


class Store:
    def __init__(self, latest="b" * 40, indexed="a" * 40):
        self.data = {
            "id": "repo-1",
            "kind": "github",
            "status": "READY",
            "source": "https://github.com/acme/shop",
            "latest_github_sha": latest,
            "indexed_sha": indexed,
        }
        self.updates = []

    def repository(self, repository_id):
        return self.data if repository_id == "repo-1" else None

    def update_repository(self, repository_id, **fields):
        self.updates.append(fields)
        self.data.update(fields)

    def fail_sync_if_active(self, repository_id, error, failed_at):
        self.update_repository(repository_id, sync_status="ERROR", sync_error=error, sync_updated_at=failed_at)


class Redis:
    def __init__(self):
        self.values = {}

    def setex(self, key, ttl, value):
        self.values[key] = value


def install_store(monkeypatch, store):
    monkeypatch.setattr(repository_sync, "get_store", lambda: store)
    repository_sync.get_store.cache_clear = lambda: None


def test_sync_coalesces_superseded_pushes(monkeypatch):
    store = Store(latest="c" * 40)
    install_store(monkeypatch, store)
    monkeypatch.setattr(
        repository_sync,
        "installation_token",
        lambda installation_id: (_ for _ in ()).throw(AssertionError("should not authenticate")),
    )

    result = repository_sync.sync_github_repository("repo-1", 42, "b" * 40)

    assert result == {"status": "SUPERSEDED", "expected_sha": "b" * 40}


def test_sync_uses_installation_token_and_preserves_repository_readiness(monkeypatch):
    store = Store()
    cache = Redis()
    install_store(monkeypatch, store)
    monkeypatch.setattr(repository_sync, "installation_token", lambda installation_id: "installation-token")
    monkeypatch.setattr(repository_sync, "redis_connection", lambda: cache)
    monkeypatch.setattr(repository_sync, "get_current_job", lambda: SimpleNamespace(id="sync-job"))

    def ingest(repository_id, kind, source, background_sync=False):
        assert (repository_id, kind, source, background_sync) == (
            "repo-1",
            "github",
            "https://github.com/acme/shop",
            True,
        )
        store.update_repository(repository_id, indexed_sha="b" * 40)

    monkeypatch.setattr(repository_sync, "ingest", ingest)

    result = repository_sync.sync_github_repository("repo-1", 42, "b" * 40)

    assert result["status"] == "CURRENT"
    assert store.data["status"] == "READY"
    assert store.data["sync_status"] == "CURRENT"
    assert cache.values["regora:github-token:sync-job"] == "installation-token"


def test_sync_failure_callback_marks_only_sync_state(monkeypatch):
    store = Store()
    install_store(monkeypatch, store)
    job = SimpleNamespace(args=("repo-1", 42, "b" * 40))

    repository_sync.sync_job_failure(job, None, TimeoutError, TimeoutError(), None)

    assert store.data["status"] == "READY"
    assert store.data["sync_status"] == "ERROR"
    assert "TimeoutError" in store.data["sync_error"]
