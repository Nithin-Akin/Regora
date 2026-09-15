import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from neo4j.exceptions import ServiceUnavailable, AuthError, SessionExpired
from redis.exceptions import RedisError
from app.config import settings
from app.graph.store import get_store
from app.api.routes import router

logging.basicConfig(level=logging.INFO, format="%(message)s")


@asynccontextmanager
async def lifespan(app):
    settings().data_dir.mkdir(parents=True, exist_ok=True)
    try:
        get_store().initialize()
    except Exception:
        logging.exception("Neo4j initialization failed; health endpoint will report unavailability")
    yield
    get_store().driver.close()


app = FastAPI(title="RepoGraph API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(router)


@app.exception_handler(ServiceUnavailable)
@app.exception_handler(SessionExpired)
@app.exception_handler(AuthError)
async def database_error(request: Request, exc):
    return JSONResponse(
        status_code=503, content={"detail": "Neo4j is unavailable. Check database health and credentials."}
    )


@app.exception_handler(RedisError)
async def redis_error(request: Request, exc):
    return JSONResponse(status_code=503, content={"detail": "Redis is unavailable. Check the ingestion queue service."})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc):
    logging.exception("Request failed: %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500, content={"detail": "An internal error occurred. Inspect backend logs for details."}
    )
