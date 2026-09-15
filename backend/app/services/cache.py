from functools import lru_cache
from redis import Redis
from app.config import settings
from app.graph.store import get_store
from app.graph.intelligence import Intelligence


@lru_cache
def redis_connection():
    return Redis.from_url(settings().redis_url, socket_connect_timeout=3, socket_timeout=5)


# Bounded process-local snapshot cache; version key invalidates all cached intelligence.
@lru_cache(maxsize=8)
def snapshot(repository_id, fingerprint):
    return Intelligence(get_store().graph(repository_id))


def intelligence(repository_id):
    meta = get_store().repository(repository_id)
    if not meta:
        raise KeyError(repository_id)
    return snapshot(repository_id, meta.get("fingerprint", "") + meta.get("updated_at", ""))
