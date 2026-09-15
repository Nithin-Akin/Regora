import logging
import os
from rq import Worker, Queue
from app.services.cache import redis_connection
from app.graph.store import get_store
from app.workers.ingestion import work_horse_killed
from app.workers.cleanup import cleanup_abandoned_files

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    get_store().initialize()
    cleanup_abandoned_files()
    connection = redis_connection()
    Worker(
        [Queue(name, connection=connection) for name in os.environ.get("WORKER_QUEUES", "ingestion").split(",")],
        connection=connection,
        work_horse_killed_handler=work_horse_killed,
    ).work()
