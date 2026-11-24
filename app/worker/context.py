"""Contesto passato ai gestori dei job: avanzamento, checkpoint per fase, annullamento."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

from app.db.models import JobStatus
from app.errors import AppError
from app.worker.queue import ClaimedJob, JobQueue

T = TypeVar("T")

PROGRESS_MIN_INTERVAL_S = 0.25
CANCEL_CHECK_INTERVAL_S = 0.5


class JobError(AppError):
    """Errore previsto di un job, con codice e messaggio comprensibile per l'utente."""


class JobCancelled(Exception):  # noqa: N818 - è un segnale, non un errore
    """L'utente ha annullato il job."""


class JobInterrupted(Exception):  # noqa: N818 - è un segnale, non un errore
    """Il worker si sta chiudendo: il job tornerà in coda dal checkpoint."""


class JobContext:
    def __init__(self, queue: JobQueue, job: ClaimedJob, stop_event: threading.Event) -> None:
        self._queue = queue
        self._job = job
        self._stop = stop_event
        self._last_report = 0.0
        self._last_cancel_check = 0.0
        self._status: JobStatus | None = None
        self._phase: str | None = None
        checkpoint = job.checkpoint or {}
        self._completed: list[str] = list(checkpoint.get("completed", []))
        self._data: dict[str, Any] = dict(checkpoint.get("data", {}))

    @property
    def job_id(self) -> str:
        return self._job.id

    @property
    def kind(self) -> str:
        return self._job.kind

    @property
    def song_id(self) -> str | None:
        return self._job.song_id

    @property
    def payload(self) -> dict[str, Any]:
        return self._job.payload

    @property
    def completed_phases(self) -> list[str]:
        return list(self._completed)

    def stage(self, status: JobStatus, phase: str, message: str | None = None) -> None:
        """Entra in una nuova fase visibile all'utente (stato del job più fase di dettaglio)."""
        self.check()
        self._status, self._phase = status, phase
        self._queue.report(self.job_id, status=status, phase=phase, message=message)
        self._last_report = time.monotonic()

    def progress(
        self, fraction: float, message: str | None = None, eta_s: float | None = None
    ) -> None:
        """Avanzamento complessivo 0..1. Le scritture sul DB sono limitate nel tempo."""
        self.check()
        now = time.monotonic()
        if now - self._last_report < PROGRESS_MIN_INTERVAL_S and fraction < 1.0:
            return
        self._last_report = now
        self._queue.report(self.job_id, progress=fraction, message=message, eta_s=eta_s)

    def check(self, *, force: bool = False) -> None:
        """Da chiamare spesso nei cicli lunghi: interrompe se annullato o in chiusura.

        La lettura del flag di annullamento dal DB è limitata nel tempo; ``force`` la esegue
        subito (utile dopo un errore di una libreria che potrebbe aver nascosto
        l'annullamento)."""
        if self._stop.is_set():
            raise JobInterrupted
        now = time.monotonic()
        if force or now - self._last_cancel_check >= CANCEL_CHECK_INTERVAL_S:
            self._last_cancel_check = now
            if self._queue.is_cancel_requested(self.job_id):
                raise JobCancelled

    def run_phase(self, name: str, fn: Callable[[], T]) -> T:
        """Esegue una fase una sola volta: se già completata in un tentativo precedente,
        restituisce il risultato salvato. Il risultato deve essere serializzabile in JSON."""
        if name in self._completed:
            return self._data.get(name)  # type: ignore[return-value]
        self.check()
        result = fn()
        self._completed.append(name)
        self._data[name] = result
        self._queue.save_checkpoint(self.job_id, {"completed": self._completed, "data": self._data})
        return result
