"""Coda di job persistente su SQLite, condivisa tra API e worker.

Ogni operazione è una transazione breve con istruzioni UPDATE condizionali
("compare and set") così che due processi non possano prendere lo stesso job e che
annullamento e avanzamento non si sovrascrivano.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Integer, delete, func, insert, literal_column, select, update
from sqlalchemy.sql.elements import ColumnClause

from app.db.base import new_id, utcnow
from app.db.models import (
    RUNNING_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
    Job,
    JobStatus,
    Worker,
)
from app.db.session import Database

log = logging.getLogger(__name__)

MAX_ERROR_MESSAGE = 1000

# Ordine di inserimento: il rowid di SQLite cresce a ogni INSERT. ``created_at`` non basta,
# perché due job creati nello stesso istante avrebbero lo stesso valore.
_INSERT_ORDER: ColumnClause[int] = literal_column("jobs.rowid", Integer)


@dataclass(frozen=True)
class ClaimedJob:
    id: str
    kind: str
    song_id: str | None
    payload: dict[str, Any]
    checkpoint: dict[str, Any]
    attempts: int


@dataclass(frozen=True)
class RecoveryReport:
    requeued: list[str]
    failed: list[str]
    cancelled: list[str]


class JobQueue:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------ lato API

    def enqueue(
        self, kind: str, payload: dict[str, Any] | None = None, song_id: str | None = None
    ) -> str:
        job_id = new_id()
        with self.db.session() as s:
            s.execute(
                insert(Job).values(
                    id=job_id,
                    kind=kind,
                    song_id=song_id,
                    payload=payload or {},
                    checkpoint={},
                    status=JobStatus.QUEUED,
                    progress=0.0,
                    message="In coda",
                )
            )
        log.info("job accodato", extra={"job_id": job_id, "kind": kind})
        return job_id

    def get(self, job_id: str) -> Job | None:
        with self.db.read_session() as s:
            return s.get(Job, job_id)

    def list_jobs(self, statuses: set[JobStatus] | None = None, limit: int = 100) -> list[Job]:
        with self.db.read_session() as s:
            stmt = select(Job).order_by(_INSERT_ORDER.desc()).limit(limit)
            if statuses:
                stmt = stmt.where(Job.status.in_(statuses))
            return list(s.scalars(stmt))

    def request_cancel(self, job_id: str) -> Job | None:
        """Annulla subito un job in coda; per uno in esecuzione chiede al worker di fermarsi.

        Restituisce lo stato aggiornato, oppure None se il job non esiste. Un job già
        terminato resta invariato.
        """
        now = utcnow()
        with self.db.session() as s:
            s.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == JobStatus.QUEUED)
                .values(
                    status=JobStatus.CANCELLED,
                    cancel_requested=True,
                    message="Annullato",
                    finished_at=now,
                    updated_at=now,
                )
            )
            s.execute(
                update(Job)
                .where(Job.id == job_id, Job.status.in_(RUNNING_JOB_STATUSES))
                .values(cancel_requested=True, message="Annullamento in corso…", updated_at=now)
            )
        return self.get(job_id)

    # --------------------------------------------------------- lato worker

    def claim(self, worker_id: str, kind_status: dict[str, JobStatus]) -> ClaimedJob | None:
        """Prende il job in coda più vecchio tra i tipi gestiti e lo porta allo stato
        iniziale del suo tipo. Restituisce None se la coda è vuota."""
        if not kind_status:
            return None
        while True:
            with self.db.session() as s:
                row = s.execute(
                    select(Job.id, Job.kind)
                    .where(Job.status == JobStatus.QUEUED, Job.kind.in_(kind_status))
                    .order_by(_INSERT_ORDER)
                    .limit(1)
                ).first()
                if row is None:
                    return None
                job_id, kind = row
                now = utcnow()
                result = s.execute(
                    update(Job)
                    .where(Job.id == job_id, Job.status == JobStatus.QUEUED)
                    .values(
                        status=kind_status[kind],
                        worker_id=worker_id,
                        attempts=Job.attempts + 1,
                        started_at=func.coalesce(Job.started_at, now),
                        message="Avvio…",
                        updated_at=now,
                    )
                )
                if result.rowcount == 1:  # type: ignore[attr-defined]
                    job = s.get_one(Job, job_id)
                    s.execute(
                        update(Worker).where(Worker.id == worker_id).values(current_job_id=job_id)
                    )
                    return ClaimedJob(
                        id=job.id,
                        kind=job.kind,
                        song_id=job.song_id,
                        payload=dict(job.payload),
                        checkpoint=dict(job.checkpoint),
                        attempts=job.attempts,
                    )
            # Un altro worker l'ha preso tra SELECT e UPDATE: si riprova.

    def report(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        phase: str | None = None,
        progress: float | None = None,
        message: str | None = None,
        eta_s: float | None = None,
    ) -> None:
        values: dict[str, Any] = {"updated_at": utcnow(), "eta_s": eta_s}
        if status is not None:
            if status not in RUNNING_JOB_STATUSES:
                raise ValueError(f"Stato non valido durante l'esecuzione: {status}")
            values["status"] = status
        if phase is not None:
            values["phase"] = phase
        if progress is not None:
            values["progress"] = min(max(progress, 0.0), 1.0)
        if message is not None:
            values["message"] = message[:500]
        with self.db.session() as s:
            s.execute(
                update(Job)
                .where(Job.id == job_id, Job.status.in_(RUNNING_JOB_STATUSES))
                .values(**values)
            )

    def save_checkpoint(self, job_id: str, checkpoint: dict[str, Any]) -> None:
        with self.db.session() as s:
            s.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(checkpoint=checkpoint, updated_at=utcnow())
            )

    def is_cancel_requested(self, job_id: str) -> bool:
        with self.db.read_session() as s:
            return bool(s.scalar(select(Job.cancel_requested).where(Job.id == job_id)))

    def complete(self, job_id: str, message: str = "Completato") -> None:
        self._finish(job_id, JobStatus.READY, message=message, progress=1.0)

    def fail(self, job_id: str, code: str, message: str) -> None:
        self._finish(
            job_id,
            JobStatus.FAILED,
            message="Errore",
            error_code=code,
            error_message=message[:MAX_ERROR_MESSAGE],
        )

    def mark_cancelled(self, job_id: str) -> None:
        self._finish(job_id, JobStatus.CANCELLED, message="Annullato")

    def requeue(self, job_id: str, *, count_attempt: bool) -> None:
        """Rimette in coda un job interrotto, conservando il checkpoint."""
        values: dict[str, Any] = {
            "status": JobStatus.QUEUED,
            "worker_id": None,
            "eta_s": None,
            "message": "In coda (ripresa dall'ultima fase completata)",
            "updated_at": utcnow(),
        }
        if not count_attempt:
            values["attempts"] = func.max(Job.attempts - 1, 0)
        with self.db.session() as s:
            s.execute(
                update(Job)
                .where(Job.id == job_id, Job.status.in_(RUNNING_JOB_STATUSES))
                .values(**values)
            )

    def _finish(self, job_id: str, status: JobStatus, **values: Any) -> None:
        now = utcnow()
        with self.db.session() as s:
            s.execute(
                update(Job)
                .where(Job.id == job_id, Job.status.not_in(TERMINAL_JOB_STATUSES))
                .values(status=status, finished_at=now, updated_at=now, eta_s=None, **values)
            )
            s.execute(
                update(Worker).where(Worker.current_job_id == job_id).values(current_job_id=None)
            )
        log.info("job terminato", extra={"job_id": job_id, "status": status.value})

    # ------------------------------------------------------------- worker

    def register_worker(self) -> str:
        worker_id = new_id()
        with self.db.session() as s:
            s.execute(insert(Worker).values(id=worker_id, pid=os.getpid(), hostname=_hostname()))
        return worker_id

    def heartbeat(self, worker_id: str) -> None:
        with self.db.session() as s:
            s.execute(update(Worker).where(Worker.id == worker_id).values(heartbeat_at=utcnow()))

    def unregister_worker(self, worker_id: str) -> None:
        with self.db.session() as s:
            s.execute(delete(Worker).where(Worker.id == worker_id))

    def live_workers(self, stale_after_s: float) -> list[Worker]:
        threshold = utcnow() - timedelta(seconds=stale_after_s)
        with self.db.read_session() as s:
            return list(s.scalars(select(Worker).where(Worker.heartbeat_at >= threshold)))

    def last_heartbeat(self) -> datetime | None:
        with self.db.read_session() as s:
            return s.scalar(select(func.max(Worker.heartbeat_at)))

    def recover_stale(self, stale_after_s: float, max_attempts: int) -> RecoveryReport:
        """Recupera i job "in esecuzione" il cui worker non dà più segni di vita.

        - annullamento richiesto → ``cancelled``;
        - tentativi esauriti → ``failed`` con codice ``worker_crashed``;
        - altrimenti → di nuovo in coda, ripartendo dal checkpoint.
        """
        threshold = utcnow() - timedelta(seconds=stale_after_s)
        requeued: list[str] = []
        failed: list[str] = []
        cancelled: list[str] = []
        with self.db.session() as s:
            s.execute(delete(Worker).where(Worker.heartbeat_at < threshold))
            # Worker su questo PC il cui processo non esiste più: morti anche se
            # l'heartbeat è recente (app chiusa male e riaperta subito).
            host = _hostname()
            local = s.execute(select(Worker.id, Worker.pid).where(Worker.hostname == host))
            dead = [wid for wid, pid in local if pid != os.getpid() and not pid_alive(pid)]
            if dead:
                s.execute(delete(Worker).where(Worker.id.in_(dead)))
            alive = select(Worker.id)
            orphans = list(
                s.execute(
                    select(Job.id, Job.attempts, Job.cancel_requested).where(
                        Job.status.in_(RUNNING_JOB_STATUSES),
                        (Job.worker_id.is_(None)) | (Job.worker_id.not_in(alive)),
                    )
                )
            )
        for job_id, attempts, cancel_requested in orphans:
            if cancel_requested:
                self.mark_cancelled(job_id)
                cancelled.append(job_id)
            elif attempts >= max_attempts:
                self.fail(
                    job_id,
                    "worker_crashed",
                    "L'elaborazione si è interrotta più volte. Controlla i log in logs/worker.log.",
                )
                failed.append(job_id)
            else:
                self.requeue(job_id, count_attempt=True)
                requeued.append(job_id)
        if orphans:
            log.warning(
                "job orfani recuperati",
                extra={"requeued": requeued, "failed": failed, "cancelled": cancelled},
            )
        return RecoveryReport(requeued=requeued, failed=failed, cancelled=cancelled)


def _hostname() -> str:
    try:
        return socket.gethostname()[:255]
    except OSError:  # pragma: no cover
        return "unknown"


def pid_alive(pid: int) -> bool:
    """Vero se il processo esiste ancora (Windows: OpenProcess + GetExitCodeProcess)."""
    if pid <= 0:
        return False
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


__all__ = ["ClaimedJob", "JobQueue", "RecoveryReport", "pid_alive"]
