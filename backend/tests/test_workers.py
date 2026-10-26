from types import SimpleNamespace

from app.workers import run


def test_worker_termination_dispatches_by_queue(monkeypatch):
    calls = []
    monkeypatch.setattr(run, "ingestion_work_horse_killed", lambda *args: calls.append("ingestion"))
    monkeypatch.setattr(run, "guardian_work_horse_killed", lambda *args: calls.append("guardian"))

    run.handle_work_horse_killed(SimpleNamespace(origin="pull-requests"), 1, 9, None)
    run.handle_work_horse_killed(SimpleNamespace(origin="ingestion"), 2, 9, None)
    run.handle_work_horse_killed(SimpleNamespace(origin="architecture"), 3, 9, None)

    assert calls == ["guardian", "ingestion"]
