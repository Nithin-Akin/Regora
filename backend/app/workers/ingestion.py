import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from rq import get_current_job
from app.config import settings
from app.graph.store import get_store
from app.graph.intelligence import Intelligence
from app.security.repositories import extract_zip, clone_github, scan_files
from app.parsers.pipeline import analyze_repository
from app.embeddings.providers import embed_graph

log = logging.getLogger("repograph.ingestion")


def now():
    return datetime.now(timezone.utc).isoformat()


def ingest(repository_id, kind, source):
    # RQ forks per job; never reuse a Neo4j connection inherited from its parent.
    get_store.cache_clear()
    store = get_store()
    started = time.monotonic()
    directory = settings().data_dir / repository_id
    destination = directory / "source"
    events = []

    def stage(status, progress, message):
        elapsed = round(time.monotonic() - started, 2)
        event = {
            "status": status,
            "progress": progress,
            "message": message,
            "elapsed_seconds": elapsed,
            "timestamp": now(),
        }
        events.append(event)
        store.update_repository(
            repository_id,
            status=status,
            progress=progress,
            message=message,
            logs=json.dumps(events[-100:]),
            updated_at=now(),
        )
        job = get_current_job()
        if job:
            job.meta.update(event)
            job.save_meta()
        log.info(json.dumps({"repository_id": repository_id, "job_id": job.id if job else repository_id, **event}))

    try:
        stage(
            "CLONING",
            5,
            "Cloning repository"
            if kind == "github"
            else "Extracting repository"
            if kind == "zip"
            else "Copying included demo",
        )
        if kind != "reindex" and destination.exists():
            shutil.rmtree(destination)
        if kind == "reindex":
            root = Path(source)
        elif kind == "github":
            root = clone_github(source, destination)
        elif kind == "zip":
            destination.mkdir(parents=True, exist_ok=True)
            root = extract_zip(Path(source), destination)
        else:
            shutil.copytree(settings().demo_dir, destination)
            root = destination
        stage("SCANNING", 15, "Scanning files and detecting languages")
        files = scan_files(root)
        languages = sorted({p.suffix for p in files})
        store.update_repository(repository_id, source_root=str(root), languages=languages)
        stage("PARSING", 22, f"Parsing syntax trees and extracting symbols from {len(files)} files")
        graph = analyze_repository(
            root,
            repository_id,
            lambda done, total: stage("PARSING", 22 + int(28 * done / total), f"Parsed {done}/{total} files"),
        )
        stage("BUILDING_GRAPH", 55, "Dependencies resolved; writing knowledge graph")
        metadata = store.repository(repository_id)
        previous = (
            store.graph(repository_id, with_embeddings=True)
            if metadata.get("embedding_model") == settings().embedding_model
            and metadata.get("embedding_provider") == settings().embedding_provider
            else None
        )
        embedding_cache = {n.id: (n.hash, n.embedding) for n in previous.nodes if n.embedding} if previous else {}
        store.save_graph(repository_id, graph)
        store.update_repository(repository_id, fingerprint=graph.fingerprint, warnings=json.dumps(graph.warnings))
        stage("EMBEDDING", 65, "Generating semantic embeddings (first run downloads the local model)")
        rows = embed_graph(
            graph,
            lambda done, total: stage(
                "EMBEDDING", 65 + int(25 * done / max(1, total)), f"Embedded {done}/{total} code units"
            ),
            embedding_cache,
        )
        store.update_embeddings(rows)
        stage("ANALYZING", 92, "Analyzing architecture, dependency hubs, and cycles")
        overview = Intelligence(graph).overview()
        store.update_repository(
            repository_id,
            overview=json.dumps(overview),
            embedding_model=settings().embedding_model,
            embedding_provider=settings().embedding_provider,
        )
        from app.models.schema import Answer, Citation
        from app.services.cache import redis_connection
        from rq import Queue

        evidence = [item["node"] for item in overview["hubs"][:4] if item["node"]["file_path"]]
        architecture = Answer(
            answer=f"The repository contains {overview['files']} source files, {overview['lines']} lines, and {overview['relationships']} extracted relationships. "
            f"Its most connected components include {', '.join(n['name'] for n in evidence)}. "
            f"{len(overview['cycles'])} dependency cycles were found.",
            confidence=1.0,
            grounding="static-evidence",
            intent="architecture",
            symbols=[n["id"] for n in evidence],
            citations=[
                Citation(symbol_id=n["id"], file=n["file_path"], start_line=n["start_line"], end_line=n["end_line"])
                for n in evidence
            ],
        )
        store.update_repository(
            repository_id, architecture=architecture.model_dump_json(), architecture_status="QUEUED"
        )
        stage("READY", 100, f"Ready · {len(graph.nodes)} nodes · {len(graph.edges)} relationships")
        try:
            Queue("architecture", connection=redis_connection()).enqueue(
                generate_architecture, repository_id, graph.fingerprint, job_timeout=600, result_ttl=3600
            )
        except Exception:
            store.update_repository(repository_id, architecture_status="EVIDENCE_ONLY")
            log.exception("Could not enqueue architecture explanation: %s", repository_id)
    except Exception as exc:
        message = (
            str(exc)[:500]
            if isinstance(exc, ValueError)
            else f"{type(exc).__name__}: ingestion failed; inspect worker logs and service health."
        )
        try:
            stage("FAILED", 0, message)
        finally:
            log.exception("Ingestion failed: repository_id=%s", repository_id)
        raise
    finally:
        if kind == "zip":
            Path(source).unlink(missing_ok=True)


# Handles RQ timeouts and worker failures outside the function's exception boundary.
def job_failure(job, connection, exc_type, exc_value, traceback):
    try:
        get_store().update_repository(
            job.args[0],
            status="FAILED",
            message=f"Worker stopped: {exc_type.__name__}. Retry indexing.",
            updated_at=now(),
        )
    except Exception:
        log.exception("Could not persist worker failure status")


def work_horse_killed(job, retpid, retval, rusage):
    """RQ does not invoke normal failure callbacks for a native-code crash."""
    if job.origin != "ingestion":
        return
    try:
        get_store().update_repository(
            job.args[0],
            status="FAILED",
            message="Parser worker terminated unexpectedly. Inspect worker logs and retry indexing.",
            updated_at=now(),
        )
    except Exception:
        log.exception("Could not persist terminated worker status")


def generate_architecture(repository_id, fingerprint):
    from app.agents.reasoning import RepoAgent
    from app.models.schema import AskRequest

    get_store.cache_clear()
    store = get_store()
    meta = store.repository(repository_id)
    if not meta or meta.get("fingerprint") != fingerprint:
        return
    result = RepoAgent(Intelligence(store.graph(repository_id)), store).ask(
        AskRequest(question="Give a brief architecture overview of the repository with source evidence.")
    )
    current = store.repository(repository_id)
    if current and current.get("fingerprint") == fingerprint:
        store.update_repository(
            repository_id,
            architecture=result.model_dump_json(),
            architecture_status="READY" if result.grounding == "llm-with-evidence" else "EVIDENCE_ONLY",
        )
