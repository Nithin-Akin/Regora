from app.graph.store import GraphStore
from app.models.schema import CodeGraph, CodeNode


def graph_store(responses):
    store = object.__new__(GraphStore)
    calls = []

    def query(cypher, **parameters):
        calls.append((cypher, parameters))
        return responses.pop(0)

    store.query = query
    return store, calls


def test_github_repository_reuses_exact_installation_binding():
    repository = {"id": "repo-1", "github_installation_id": 42}
    store, calls = graph_store([[{"repo": repository}]])
    result = store.github_repository("acme", "shop", 42)
    assert result == {"status": "BOUND", "repository": repository}
    assert len(calls) == 1


def test_github_repository_claims_single_unbound_copy_atomically():
    unbound = {"id": "repo-1", "github_installation_id": None}
    bound = {**unbound, "github_installation_id": 42}
    store, calls = graph_store([[], [{"repo": unbound}], [{"repo": bound}]])
    result = store.github_repository("acme", "shop", 42)
    assert result == {"status": "BOUND", "repository": bound}
    assert "github_installation_id IS NULL" in calls[2][0]
    assert calls[2][1]["repository_id"] == "repo-1"


def test_github_repository_rejects_ambiguous_unbound_copies():
    store, calls = graph_store(
        [
            [],
            [
                {"repo": {"id": "repo-1", "github_installation_id": None}},
                {"repo": {"id": "repo-2", "github_installation_id": None}},
            ],
        ]
    )
    result = store.github_repository("acme", "shop", 42)
    assert result == {"status": "AMBIGUOUS", "repository": None}
    assert len(calls) == 2


def test_github_repository_reports_cross_installation_claim_race():
    unbound = {"id": "repo-1", "github_installation_id": None}
    store, _ = graph_store([[], [{"repo": unbound}], [], []])
    result = store.github_repository("acme", "shop", 42)
    assert result == {"status": "CONFLICT", "repository": None}


def test_guardian_worker_failure_only_updates_active_runs():
    failed = {"id": "run-1", "status": "ERROR"}
    store, calls = graph_store([[{"run": failed}]])

    result = store.fail_guardian_run_if_active("run-1", "worker stopped", "2026-10-26T00:00:00Z")

    assert result == failed
    assert "g.status IN ['QUEUED', 'RUNNING']" in calls[0][0]
    assert calls[0][1]["error"] == "worker stopped"


def test_sync_worker_failure_preserves_ready_repository():
    repository = {"id": "repo-1", "status": "READY", "sync_status": "ERROR"}
    store, calls = graph_store([[{"repo": repository}]])

    result = store.fail_sync_if_active("repo-1", "worker stopped", "2026-10-29T00:00:00Z")

    assert result == repository
    assert "r.sync_status IN" in calls[0][0]
    assert "r.status" not in calls[0][0]


def test_graph_snapshot_is_idempotent_and_history_is_bounded():
    graph = CodeGraph(
        nodes=[CodeNode(id="node-1", name="one", type="Function", repository_id="repo-1")],
        fingerprint="fingerprint-1",
    )
    saved = {
        "id": "snapshot-1",
        "repository_id": "repo-1",
        "commit_sha": "a" * 40,
        "nodes": 1,
        "relationships": 0,
    }
    store, calls = graph_store([[{"snapshot": saved}], []])

    result = store.save_graph_snapshot("repo-1", "a" * 40, graph, "2026-10-29T00:00:00Z", "push")

    assert result == saved
    assert "MERGE (s:GraphSnapshot" in calls[0][0]
    assert calls[0][1]["data"]["commit_sha"] == "a" * 40
    assert calls[0][1]["data"]["format"] == "zlib-json-v1"
    assert "SKIP $keep" in calls[1][0]
    assert calls[1][1]["keep"] == 20


def test_graph_publication_uses_one_transaction_for_graph_snapshot_and_metadata():
    calls = []

    class Result:
        def consume(self):
            return None

    class Transaction:
        def run(self, cypher, **parameters):
            calls.append((cypher, parameters))
            return Result()

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute_write(self, callback):
            callback(Transaction())

    class Driver:
        def session(self):
            return Session()

    store = object.__new__(GraphStore)
    store.driver = Driver()
    graph = CodeGraph(
        nodes=[CodeNode(id="node-1", name="one", type="Function", repository_id="repo-1")],
        fingerprint="fingerprint-1",
    )

    store.publish_graph(
        "repo-1",
        graph,
        {"fingerprint": "fingerprint-1", "overview": "{}"},
        {"commit_sha": "a" * 40, "created_at": "2026-10-31T00:00:00Z", "trigger": "push"},
    )

    statements = [cypher for cypher, _ in calls]
    assert any("DETACH DELETE n" in statement for statement in statements)
    assert any("MERGE (s:GraphSnapshot" in statement for statement in statements)
    assert any("SET r += $fields" in statement for statement in statements)
    assert calls[-1][1]["fields"]["fingerprint"] == "fingerprint-1"
