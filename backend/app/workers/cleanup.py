"""Remove orphan work directories and expired temporary uploads; retain indexed source."""

import logging
import shutil
import time
from uuid import UUID
from app.config import settings
from app.graph.store import get_store


def cleanup_abandoned_files(max_age_seconds=86400):
    root = settings().data_dir
    if not root.exists():
        return
    store = get_store()
    for directory in root.iterdir():
        if directory.is_symlink() or not directory.is_dir():
            continue
        try:
            UUID(directory.name)
        except ValueError:
            continue
        if time.time() - directory.stat().st_mtime < max_age_seconds:
            continue
        metadata = store.repository(directory.name)
        if metadata is None:
            shutil.rmtree(directory)
            logging.info("Removed orphan repository work directory: %s", directory.name)
        elif metadata.get("status") in {"READY", "FAILED"}:
            (directory / "upload.zip").unlink(missing_ok=True)
