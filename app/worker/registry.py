"""Registro dei tipi di job e dei loro gestori."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.config import Settings
from app.db.models import JobStatus
from app.db.session import Database
from app.worker.context import JobContext

HandlerFn = Callable[[JobContext], None]


@dataclass(frozen=True)
class JobHandler:
    kind: str
    initial_status: JobStatus
    run: HandlerFn


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, kind: str, initial_status: JobStatus, run: HandlerFn) -> None:
        if not initial_status.is_running:
            raise ValueError(f"Lo stato iniziale deve essere di esecuzione: {initial_status}")
        if kind in self._handlers:
            raise ValueError(f"Tipo di job già registrato: {kind}")
        self._handlers[kind] = JobHandler(kind, initial_status, run)

    def get(self, kind: str) -> JobHandler | None:
        return self._handlers.get(kind)

    def kind_status(self) -> dict[str, JobStatus]:
        return {k: h.initial_status for k, h in self._handlers.items()}


def default_registry(settings: Settings, db: Database) -> HandlerRegistry:
    """Gestori dell'app. Le fasi successive (analisi, separazione, testi) si registrano qui."""
    from app.analysis import jobs as analysis_jobs
    from app.importing import jobs as import_jobs
    from app.separation import jobs as separation_jobs

    registry = HandlerRegistry()
    import_jobs.register(registry, settings, db)
    analysis_jobs.register(registry, settings, db)
    separation_jobs.register(registry, settings, db)
    return registry
