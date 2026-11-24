"""Schemi Pydantic delle risposte API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import Job, JobStatus


class DatabaseHealth(BaseModel):
    ok: bool
    revision: str | None
    head: str | None


class WorkerHealth(BaseModel):
    alive: bool
    last_heartbeat: datetime | None


class FfmpegHealth(BaseModel):
    available: bool
    path: str | None


class HealthOut(BaseModel):
    status: str
    version: str
    database: DatabaseHealth
    worker: WorkerHealth
    ffmpeg: FfmpegHealth
    youtube_enabled: bool
    lrclib_enabled: bool


class JobErrorOut(BaseModel):
    code: str
    message: str


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    song_id: str | None
    kind: str
    status: JobStatus
    phase: str | None
    progress: float
    message: str | None
    eta_s: float | None
    error: JobErrorOut | None
    cancel_requested: bool
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime

    @classmethod
    def from_job(cls, job: Job) -> JobOut:
        error = (
            JobErrorOut(code=job.error_code, message=job.error_message or "")
            if job.error_code
            else None
        )
        return cls(
            id=job.id,
            song_id=job.song_id,
            kind=job.kind,
            status=job.status,
            phase=job.phase,
            progress=job.progress,
            message=job.message,
            eta_s=job.eta_s,
            error=error,
            cancel_requested=job.cancel_requested,
            attempts=job.attempts,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            updated_at=job.updated_at,
        )
