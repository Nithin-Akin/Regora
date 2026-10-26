from app.graph.store import GraphStore


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
