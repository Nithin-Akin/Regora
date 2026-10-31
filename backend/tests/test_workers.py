from types import SimpleNamespace

import pytest

from app.workers import run
from app.workers import ingestion
from app.models.schema import CodeGraph, CodeNode


def test_worker_termination_dispatches_by_queue(monkeypatch):
    calls = []
    monkeypatch.setattr(run, "ingestion_work_horse_killed", lambda *args: calls.append("ingestion"))
    monkeypatch.setattr(run, "guardian_work_horse_killed", lambda *args: calls.append("guardian"))
    monkeypatch.setattr(run, "sync_work_horse_killed", lambda *args: calls.append("sync"))

    run.handle_work_horse_killed(SimpleNamespace(origin="pull-requests"), 1, 9, None)
    run.handle_work_horse_killed(SimpleNamespace(origin="ingestion"), 2, 9, None)
    run.handle_work_horse_killed(SimpleNamespace(origin="architecture"), 3, 9, None)
    run.handle_work_horse_killed(SimpleNamespace(origin="sync"), 4, 9, None)

    assert calls == ["guardian", "ingestion", "sync"]


def test_ingestion_does_not_publish_graph_when_analysis_fails(monkeypatch, tmp_path):
    class Store:
        published = False

        def update_repository(self, repository_id, **fields):
            pass

        def repository(self, repository_id):
            return {}

        def publish_graph(self, repository_id, graph, repository_fields, snapshot):
            self.published = True

    store = Store()
    graph = CodeGraph(
        nodes=[CodeNode(id="node-1", name="one", type="Function", repository_id="repo-1")],
        fingerprint="fingerprint-1",
    )
    monkeypatch.setattr(ingestion, "get_store", lambda: store)
    ingestion.get_store.cache_clear = lambda: None
    monkeypatch.setattr(ingestion, "scan_files", lambda root: [root / "app.py"])
    monkeypatch.setattr(ingestion, "analyze_repository", lambda *args: graph)
    monkeypatch.setattr(ingestion, "embed_graph", lambda *args: [])
    monkeypatch.setattr(
        ingestion,
        "load_architecture_policy",
        lambda *args: (_ for _ in ()).throw(ValueError("invalid architecture policy")),
    )

    with pytest.raises(ValueError, match="invalid architecture policy"):
        ingestion.ingest("repo-1", "reindex", str(tmp_path))

    assert store.published is False
