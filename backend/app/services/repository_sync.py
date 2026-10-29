"""Continuous default-branch synchronization for installed GitHub repositories."""

import logging
from datetime import UTC, datetime

from rq import get_current_job

from app.config import settings
from app.graph.store import get_store
from app.services.cache import redis_connection
from app.services.github_app import installation_token
from app.workers.ingestion import ingest

log = logging.getLogger("regora.repository_sync")


def now() -> str:
    return datetime.now(UTC).isoformat()


def sync_github_repository(repository_id: str, installation_id: int, expected_sha: str) -> dict:
    get_store.cache_clear()
    store = get_store()
    repository = store.repository(repository_id)
    if not repository or repository.get("kind") != "github":
        raise ValueError("The GitHub repository is unavailable for synchronization")
    if repository.get("latest_github_sha") != expected_sha:
        return {"status": "SUPERSEDED", "expected_sha": expected_sha}
    if repository.get("indexed_sha") == expected_sha:
        store.update_repository(
            repository_id,
            sync_status="CURRENT",
            sync_progress=100,
            sync_message="Already synchronized",
            sync_error="",
            sync_updated_at=now(),
        )
        return {"status": "CURRENT", "indexed_sha": expected_sha}
    try:
        token = installation_token(installation_id)
        job = get_current_job()
        if not job:
            raise RuntimeError("Synchronization must run inside a worker")
        redis_connection().setex(
            f"regora:github-token:{job.id}",
            settings().job_timeout + 3600,
            token,
        )
        ingest(repository_id, "github", repository["source"], background_sync=True)
        current = get_store().repository(repository_id)
        indexed_sha = current.get("indexed_sha", "")
        latest_sha = current.get("latest_github_sha", "")
        status = "CURRENT" if indexed_sha == latest_sha else "STALE"
        get_store().update_repository(
            repository_id,
            sync_status=status,
            sync_progress=100,
            sync_message="Repository synchronized" if status == "CURRENT" else "A newer push is waiting",
            sync_error="",
            last_synced_at=now(),
            sync_updated_at=now(),
        )
        return {"status": status, "indexed_sha": indexed_sha, "latest_github_sha": latest_sha}
    except Exception as exc:
        message = str(exc)[:300] if isinstance(exc, (RuntimeError, ValueError)) else "Repository synchronization failed"
        try:
            get_store().update_repository(
                repository_id,
                sync_status="ERROR",
                sync_error=message,
                sync_message="Synchronization failed",
                sync_updated_at=now(),
            )
        except Exception:
            log.exception("Could not persist synchronization failure")
        raise


def sync_job_failure(job, connection, exc_type, exc_value, traceback):
    try:
        get_store().fail_sync_if_active(
            job.args[0],
            f"Worker stopped: {exc_type.__name__}. Retry synchronization.",
            now(),
        )
    except Exception:
        log.exception("Could not persist synchronization worker failure")


def sync_work_horse_killed(job, retpid, retval, rusage):
    try:
        get_store().fail_sync_if_active(
            job.args[0],
            "Synchronization worker terminated unexpectedly. Retry synchronization.",
            now(),
        )
    except Exception:
        log.exception("Could not persist terminated synchronization worker status")
