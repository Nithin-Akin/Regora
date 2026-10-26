import logging
import os

from rq import Queue, Worker

from app.graph.store import get_store
from app.services.cache import redis_connection
from app.services.pr_guardian import guardian_work_horse_killed
from app.workers.cleanup import cleanup_abandoned_files
from app.workers.ingestion import work_horse_killed as ingestion_work_horse_killed


def handle_work_horse_killed(job, retpid, retval, rusage):
    if job.origin == "ingestion":
        ingestion_work_horse_killed(job, retpid, retval, rusage)
    elif job.origin == "pull-requests":
        guardian_work_horse_killed(job, retpid, retval, rusage)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    get_store().initialize()
    cleanup_abandoned_files()
    connection = redis_connection()
    Worker(
        [Queue(name, connection=connection) for name in os.environ.get("WORKER_QUEUES", "ingestion").split(",")],
        connection=connection,
        work_horse_killed_handler=handle_work_horse_killed,
    ).work()
