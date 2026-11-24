"""Schemi Pydantic delle risposte API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import Job, JobStatus, Song, SongStatus, SourceType


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


# ------------------------------------------------------------------- brani


class SongRef(BaseModel):
    id: str
    title: str
    artist: str | None


class SongOut(BaseModel):
    id: str
    title: str
    artist: str | None
    album: str | None
    duration_s: float | None
    status: SongStatus
    source_type: SourceType
    source_url: str | None
    key: str | None
    bpm: float | None
    created_at: datetime
    updated_at: datetime
    job: JobOut | None
    audio_url: str | None
    transpose: int
    capo: int
    simplification: str

    @classmethod
    def from_song(cls, song: Song, job: Job | None, *, has_audio: bool = False) -> SongOut:
        return cls(
            id=song.id,
            title=song.title,
            artist=song.artist,
            album=song.album,
            duration_s=song.duration_s,
            status=song.status,
            source_type=song.source_type,
            source_url=song.source_url,
            key=song.key,
            bpm=song.bpm,
            created_at=song.created_at,
            updated_at=song.updated_at,
            job=JobOut.from_job(job) if job is not None else None,
            audio_url=f"/api/songs/{song.id}/audio" if has_audio else None,
            transpose=song.transpose,
            capo=song.capo,
            simplification=song.simplification.value,
        )


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


Title = Annotated[str, Field(min_length=1, max_length=500)]
OptionalText = Annotated[str | None, Field(default=None, max_length=500)]


class SongMetadataIn(BaseModel):
    title: Title
    artist: OptionalText = None
    album: OptionalText = None

    @field_validator("title", mode="before")
    @classmethod
    def _strip_title(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("artist", "album", mode="after")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class UploadPreviewOut(BaseModel):
    upload_id: str
    filename: str
    size_bytes: int
    format: str
    codec: str | None
    duration_s: float | None
    sample_rate: int | None
    channels: int | None
    title: str
    artist: str | None
    album: str | None
    duplicate_of: SongRef | None


class UrlIn(BaseModel):
    url: Annotated[str, Field(min_length=1, max_length=2000)]


class UrlPreviewOut(BaseModel):
    url: str
    title: str
    artist: str | None
    album: str | None
    duration_s: float | None
    duplicate_of: SongRef | None


class ImportUrlIn(SongMetadataIn):
    url: Annotated[str, Field(min_length=1, max_length=2000)]


class ImportStartedOut(BaseModel):
    song: SongOut
    job: JobOut
