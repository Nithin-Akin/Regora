import json
import shutil
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from rq import Queue
from app.config import settings
from app.graph.store import get_store, GraphStore
from app.services.cache import redis_connection, intelligence, snapshot
from app.workers.ingestion import ingest, job_failure, now
from app.security.repositories import validate_github
from app.models.schema import GitHubRequest, PullRequestRequest, AskRequest, TraceRequest
from app.retrieval.hybrid import HybridRetrieval
from app.agents.reasoning import RepoAgent
from app.services.pull_requests import (
    analyze_pull_request,
    fetch_pull_request,
    validate_pull_request_repository,
)

router = APIRouter(prefix="/api")
ACTIVE = {"QUEUED", "CLONING", "SCANNING", "PARSING", "BUILDING_GRAPH", "EMBEDDING", "ANALYZING"}


def repo_or_404(id, store):
    repo = store.repository(id)
    if not repo:
        raise HTTPException(404, "Repository not found")
    return repo


def ready(id, store=Depends(get_store)):
    repo = repo_or_404(id, store)
    if repo["status"] != "READY":
        raise HTTPException(409, "Repository is not ready. Check indexing status.")
    return intelligence(id)


def public_repo(repo):
    data = {k: v for k, v in repo.items() if k not in {"source_root", "source", "overview"}}
    for key in ("logs", "warnings"):
        if isinstance(data.get(key), str):
            data[key] = json.loads(data[key])
    return data


def enqueue(kind, source, name, store, id=None):
    id = id or str(uuid4())
    redis_connection().ping()
    job_id = str(uuid4())
    data = {
        "id": id,
        "name": name[:150],
        "kind": kind,
        "source": source,
        "status": "QUEUED",
        "progress": 0,
        "message": "Waiting for an ingestion worker",
        "job_id": job_id,
        "created_at": now(),
        "updated_at": now(),
        "logs": "[]",
    }
    store.create_repository(data)
    try:
        Queue("ingestion", connection=redis_connection()).enqueue(
            ingest,
            id,
            kind,
            source,
            job_id=job_id,
            job_timeout=settings().job_timeout,
            result_ttl=86400,
            failure_ttl=604800,
            on_failure=job_failure,
        )
    except Exception:
        store.update_repository(id, status="FAILED", message="Could not enqueue ingestion; check Redis and retry.")
        raise
    return public_repo(data)


@router.get("/health")
def health(store: GraphStore = Depends(get_store)):
    store.query("RETURN 1 AS ok")
    redis_connection().ping()
    return {"status": "ok"}


@router.post("/repositories/github", status_code=202)
def github(body: GitHubRequest, store: GraphStore = Depends(get_store)):
    try:
        url = validate_github(body.url)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return enqueue("github", url, url.rstrip("/").split("/")[-1].removesuffix(".git"), store)


@router.post("/repositories/demo", status_code=202)
def demo(store: GraphStore = Depends(get_store)):
    if not settings().demo_dir.is_dir():
        raise HTTPException(503, "The included demo directory is unavailable")
    return enqueue("demo", "included-demo", "Northstar Commerce", store)


@router.post("/repositories/upload", status_code=202)
async def upload(file: UploadFile = File(...), store: GraphStore = Depends(get_store)):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(422, "Choose a .zip repository archive")
    id = str(uuid4())
    directory = settings().data_dir / id
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "upload.zip"
    size = 0
    try:
        with archive.open("wb") as target:
            while chunk := await file.read(65536):
                size += len(chunk)
                if size > settings().max_archive_mb * 1024**2:
                    raise HTTPException(413, "Archive exceeds upload size limit")
                target.write(chunk)
        import zipfile

        if not zipfile.is_zipfile(archive):
            raise HTTPException(422, "This file is not a valid ZIP archive")
        return enqueue("zip", str(archive), Path(file.filename).stem, store, id)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    finally:
        await file.close()


@router.get("/repositories")
def repositories(store: GraphStore = Depends(get_store)):
    return [public_repo(r) for r in store.repositories()]


@router.get("/repositories/{id}")
@router.get("/repositories/{id}/status")
def repository(id: str, store: GraphStore = Depends(get_store)):
    repo = repo_or_404(id, store)
    if repo["status"] in ACTIVE and repo.get("job_id"):
        job = Queue("ingestion", connection=redis_connection()).fetch_job(repo["job_id"])
        if job and job.is_failed:
            store.update_repository(
                id,
                status="FAILED",
                message="The ingestion worker failed. Retry indexing or inspect worker logs.",
                updated_at=now(),
            )
            repo = store.repository(id)
    return public_repo(repo)


@router.delete("/repositories/{id}", status_code=204)
def delete(id: str, store: GraphStore = Depends(get_store)):
    repo = repo_or_404(id, store)
    if repo["status"] in ACTIVE:
        raise HTTPException(409, "Wait for indexing to finish before deleting this repository")
    store.delete_repository(id)
    directory = settings().data_dir / id
    if directory.parent.resolve() == settings().data_dir.resolve():
        shutil.rmtree(directory, ignore_errors=True)
    snapshot.cache_clear()


@router.post("/repositories/{id}/reindex", status_code=202)
def reindex(id: str, store: GraphStore = Depends(get_store)):
    repo = repo_or_404(id, store)
    if repo["status"] in ACTIVE:
        raise HTTPException(409, "Indexing is already in progress")
    kind = (
        "github"
        if repo["kind"] == "github"
        else "reindex"
        if repo.get("source_root")
        else "demo"
        if repo["kind"] == "demo"
        else None
    )
    if not kind:
        raise HTTPException(409, "Extraction failed; upload the archive again")
    redis_connection().ping()
    job_id = str(uuid4())
    store.update_repository(
        id, status="QUEUED", progress=0, job_id=job_id, message="Waiting to reindex", updated_at=now()
    )
    try:
        Queue("ingestion", connection=redis_connection()).enqueue(
            ingest,
            id,
            kind,
            repo.get("source_root") if kind == "reindex" else repo["source"],
            job_id=job_id,
            job_timeout=settings().job_timeout,
            on_failure=job_failure,
        )
    except Exception:
        store.update_repository(id, status="FAILED", message="Could not enqueue reindex")
        raise
    return public_repo(store.repository(id))


@router.get("/repositories/{id}/overview")
def overview(id: str, i=Depends(ready), store: GraphStore = Depends(get_store)):
    result = i.overview()
    metadata = store.repository(id)
    result["warnings"] = json.loads(metadata.get("warnings", "[]"))
    result["architecture"] = json.loads(metadata["architecture"]) if metadata.get("architecture") else None
    return result


@router.get("/repositories/{id}/graph")
def graph(
    id: str,
    view: str = "architecture",
    symbol_id: str | None = None,
    depth: int = Query(1, ge=0, le=5),
    types: str = "",
    relationships: str = "",
    limit: int = Query(250, ge=1, le=500),
    module: str = "",
    i=Depends(ready),
):
    if symbol_id:
        if symbol_id not in i.nodes:
            raise HTTPException(404, "Symbol not found")
        result = i.neighbors(symbol_id, depth, relationships.split(",") if relationships else None, limit=limit)
    elif view == "architecture":
        return i.architecture()
    else:
        selected = [
            n.id
            for n in i.graph.nodes
            if n.type not in {"Repository", "Directory", "UnresolvedSymbol"}
            and (not types or n.type in types.split(","))
            and (
                not module
                or n.module == module
                or (module == "External packages" and n.type == "ExternalPackage")
                or (module == "Database" and n.type == "DatabaseEntity")
            )
        ]
        result = i.subgraph(selected, limit)
    if types:
        result["nodes"] = [n for n in result["nodes"] if n["type"] in types.split(",")]
    node_ids = {n["id"] for n in result["nodes"]}
    result["edges"] = [
        e
        for e in result["edges"]
        if e["source"] in node_ids
        and e["target"] in node_ids
        and (not relationships or e["type"] in relationships.split(","))
    ]
    return result


@router.get("/repositories/{id}/files")
def files(id: str, i=Depends(ready)):
    return [i.public_node(n.id) for n in i.graph.nodes if n.type == "File"]


@router.get("/repositories/{id}/source")
def source(id: str, path: str = Query(max_length=1000), i=Depends(ready)):
    # Retrieve indexed source; user paths never reach the filesystem.
    file = next((n for n in i.graph.nodes if n.type == "File" and n.file_path == path), None)
    if not file:
        raise HTTPException(404, "Indexed source file not found")
    return file.model_dump(exclude={"embedding"})


@router.get("/repositories/{id}/symbols/{symbol_id}")
def symbol(id: str, symbol_id: str, i=Depends(ready)):
    if symbol_id not in i.nodes:
        raise HTTPException(404, "Symbol not found")
    return {
        "node": i.nodes[symbol_id].model_dump(exclude={"embedding"}),
        "incoming": [e.model_dump() for e in i.graph.edges if e.target == symbol_id][:100],
        "outgoing": [e.model_dump() for e in i.graph.edges if e.source == symbol_id][:100],
        "neighbors": i.neighbors(symbol_id, 1, limit=100),
    }


@router.get("/repositories/{id}/symbols/{symbol_id}/neighbors")
def neighbors(
    id: str,
    symbol_id: str,
    depth: int = Query(1, ge=0, le=5),
    direction: str = Query("both", pattern="^(in|out|both)$"),
    relationships: str = "",
    i=Depends(ready),
):
    if symbol_id not in i.nodes:
        raise HTTPException(404, "Symbol not found")
    return i.neighbors(symbol_id, depth, relationships.split(",") if relationships else None, direction)


@router.get("/repositories/{id}/symbols/{symbol_id}/impact")
def impact(id: str, symbol_id: str, i=Depends(ready)):
    if symbol_id not in i.nodes:
        raise HTTPException(404, "Symbol not found")
    return i.impact(symbol_id)


@router.post("/repositories/{id}/pull-request-impact")
def pull_request_impact(
    id: str,
    body: PullRequestRequest,
    i=Depends(ready),
    store: GraphStore = Depends(get_store),
):
    repo = repo_or_404(id, store)
    try:
        validate_pull_request_repository(repo, body.url)
        return analyze_pull_request(i, repo, fetch_pull_request(body.url))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/repositories/{id}/paths")
def paths(id: str, source_id: str, target_id: str, directed: bool = True, i=Depends(ready)):
    if source_id not in i.nodes or target_id not in i.nodes:
        raise HTTPException(404, "Source or target symbol not found")
    path = i.path(source_id, target_id, directed)
    return {"path": path, "graph": i.subgraph(path), "directed": directed}


@router.get("/repositories/{id}/search")
def search(
    id: str,
    q: str = Query(min_length=1, max_length=1000),
    mode: str = Query("hybrid", pattern="^(symbol|text|semantic|hybrid)$"),
    top_k: int = Query(15, ge=1, le=50),
    i=Depends(ready),
    store: GraphStore = Depends(get_store),
):
    return HybridRetrieval(i, store).search(q, mode, top_k)


@router.post("/repositories/{id}/ask")
def ask(id: str, request: AskRequest, i=Depends(ready), store: GraphStore = Depends(get_store)):
    if request.symbol_id and request.symbol_id not in i.nodes:
        raise HTTPException(404, "Selected symbol not found")
    return RepoAgent(i, store).ask(request)


@router.get("/repositories/{id}/chat/{session_id}")
def conversation(id: str, session_id: str, i=Depends(ready), store: GraphStore = Depends(get_store)):
    return store.session(id + ":" + session_id, id)


@router.post("/repositories/{id}/trace")
def trace(id: str, body: TraceRequest, i=Depends(ready)):
    if body.source_id not in i.nodes or (body.target_id and body.target_id not in i.nodes):
        raise HTTPException(404, "Symbol not found")
    if body.target_id:
        path = i.path(body.source_id, body.target_id)
        return {"paths": [path] if path else [], "graph": i.subgraph(path)}
    return i.trace(body.source_id)
