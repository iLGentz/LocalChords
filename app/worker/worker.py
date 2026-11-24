"""Ciclo principale del worker: heartbeat, recupero dei job orfani, esecuzione."""

from __future__ import annotations

import logging
import threading
import time

from app.config import Settings
from app.db.session import Database
from app.errors import AppError
from app.worker.context import JobCancelled, JobContext, JobInterrupted
from app.worker.queue import ClaimedJob, JobQueue
from app.worker.registry import HandlerRegistry

log = logging.getLogger(__name__)

RECOVERY_INTERVAL_S = 15.0


class JobWorker:
    def __init__(self, settings: Settings, db: Database, registry: HandlerRegistry) -> None:
        self.settings = settings
        self.queue = JobQueue(db)
        self.registry = registry
        self.stop_event = threading.Event()
        self.worker_id: str | None = None

    def run(self, *, until_idle: bool = False) -> None:
        """Esegue i job finché ``stop_event`` non viene impostato.

        Con ``until_idle`` si ferma appena la coda è vuota (usato nei test).
        """
        self.worker_id = self.queue.register_worker()
        log.info("worker avviato", extra={"worker_id": self.worker_id})
        hb = threading.Thread(target=self._heartbeat_loop, name="heartbeat", daemon=True)
        hb.start()
        last_recovery = 0.0
        try:
            while not self.stop_event.is_set():
                if time.monotonic() - last_recovery >= RECOVERY_INTERVAL_S:
                    self.queue.recover_stale(
                        self.settings.worker_stale_after_s, self.settings.job_max_attempts
                    )
                    last_recovery = time.monotonic()
                job = self.queue.claim(self.worker_id, self.registry.kind_status())
                if job is None:
                    if until_idle:
                        break
                    self.stop_event.wait(self.settings.worker_poll_interval_s)
                    continue
                self.execute(job)
        finally:
            self.stop_event.set()
            hb.join(timeout=2)
            self.queue.unregister_worker(self.worker_id)
            log.info("worker fermato", extra={"worker_id": self.worker_id})

    def execute(self, job: ClaimedJob) -> None:
        handler = self.registry.get(job.kind)
        extra = {"job_id": job.id, "kind": job.kind, "attempt": job.attempts}
        if handler is None:  # pragma: no cover - claim prende solo tipi registrati
            self.queue.fail(job.id, "unknown_job_kind", f"Tipo di job sconosciuto: {job.kind}")
            return
        ctx = JobContext(self.queue, job, self.stop_event)
        started = time.monotonic()
        log.info("job avviato", extra=extra)
        try:
            handler.run(ctx)
        except JobCancelled:
            self.queue.mark_cancelled(job.id)
        except JobInterrupted:
            log.info("job interrotto dalla chiusura del worker", extra=extra)
            self.queue.requeue(job.id, count_attempt=False)
        except AppError as exc:  # JobError e gli errori previsti dei moduli (es. MediaError)
            log.warning("job fallito", extra={**extra, "code": exc.code, "error": exc.message})
            self.queue.fail(job.id, exc.code, exc.message)
        except Exception:
            log.exception("errore inatteso nel job", extra=extra)
            self.queue.fail(
                job.id,
                "internal_error",
                "Errore inatteso durante l'elaborazione. I dettagli sono in logs/worker.log.",
            )
        else:
            self.queue.complete(job.id)
        finally:
            log.info(
                "job concluso", extra={**extra, "elapsed_s": round(time.monotonic() - started, 3)}
            )

    def _heartbeat_loop(self) -> None:
        assert self.worker_id is not None
        while not self.stop_event.wait(self.settings.worker_heartbeat_interval_s):
            try:
                self.queue.heartbeat(self.worker_id)
            except Exception:  # pragma: no cover - DB temporaneamente bloccato
                log.exception("heartbeat non riuscito")
