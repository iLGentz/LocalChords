"""Avvio del processo worker: ``python -m app.worker``.

Opzioni:
  --watch-stdin  si chiude quando lo stdin viene chiuso (usato da app/desktop.py, così il
                 worker non resta orfano se la finestra si chiude o va in crash).
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from types import FrameType

from app.config import Settings, get_settings
from app.db.migrate import current_revision, head_revision, upgrade_to_head
from app.db.session import Database
from app.logging_setup import configure_logging
from app.worker.registry import default_registry
from app.worker.worker import JobWorker

log = logging.getLogger("app.worker")

THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "ORT_NUM_THREADS",
)


def apply_cpu_limit(settings: Settings) -> None:
    """Limita i thread delle librerie numeriche (da fare prima di importarle)."""
    if settings.cpu_threads > 0:
        for var in THREAD_ENV_VARS:
            os.environ[var] = str(settings.cpu_threads)


def wait_for_schema(db: Database, timeout_s: float = 30.0) -> None:
    """L'app applica le migrazioni all'avvio; il worker attende e, se serve, le applica."""
    head = head_revision()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if current_revision(db.engine) == head:
            return
        time.sleep(0.5)
    upgrade_to_head(db.url)


def _watch_stdin(stop: threading.Event) -> None:
    stream = sys.stdin
    if stream is None:
        return
    try:
        while stream.readline():
            pass
    except (OSError, ValueError):
        pass
    stop.set()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="localchords-worker")
    parser.add_argument("--watch-stdin", action="store_true")
    args = parser.parse_args(argv)

    settings = get_settings()
    settings.ensure_dirs()
    configure_logging(settings.logs_dir, "worker", settings.log_level.value)
    apply_cpu_limit(settings)

    db = Database(settings.database_path)
    wait_for_schema(db)
    worker = JobWorker(settings, db, default_registry(settings, db))

    def _stop(_signum: int, _frame: FrameType | None) -> None:
        worker.stop_event.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _stop)
    if args.watch_stdin:
        threading.Thread(
            target=_watch_stdin, args=(worker.stop_event,), name="stdin-watch", daemon=True
        ).start()

    try:
        worker.run()
    finally:
        db.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
