"""Job di importazione: da file locale (``import_file``) o da YouTube (``import_url``).

Fasi (ognuna con checkpoint, quindi ripristinabili):
    download   solo per YouTube: scarica l'audio originale              stato `downloading`
    probe      rilegge il file con ffprobe e valida formato e durata    stato `analyzing`
    normalize  converte in FLAC 44,1 kHz stereo e misura il picco       stato `analyzing`
    finalize   registra l'audio normalizzato e segna il brano pronto    stato `analyzing`
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from functools import partial
from typing import Any

from sqlalchemy import delete, select

from app.adapters.youtube import YouTubeAdapter
from app.config import Settings
from app.db.models import (
    AssetKind,
    AudioAsset,
    JobStatus,
    Song,
    SongStatus,
    TimingSample,
)
from app.db.session import Database
from app.errors import AppError
from app.importing.service import IMPORT_FILE, IMPORT_URL, SongService
from app.importing.validation import check_not_silent, check_probe
from app.media.ffmpeg import MediaTools, ProbeResult
from app.storage.files import NORMALIZED_NAME, Storage, sha256_file
from app.worker.context import JobContext, JobError
from app.worker.queue import JobQueue
from app.worker.registry import HandlerRegistry

log = logging.getLogger(__name__)

# Quote dell'avanzamento complessivo per fase.
_SPANS_FILE = {"probe": (0.0, 0.05), "normalize": (0.05, 0.97), "finalize": (0.97, 1.0)}
_SPANS_URL = {
    "download": (0.0, 0.5),
    "probe": (0.5, 0.52),
    "normalize": (0.52, 0.97),
    "finalize": (0.97, 1.0),
}


def register(registry: HandlerRegistry, settings: Settings, db: Database) -> None:
    registry.register(IMPORT_FILE, JobStatus.ANALYZING, partial(run_import, settings, db))
    registry.register(IMPORT_URL, JobStatus.DOWNLOADING, partial(run_import, settings, db))


def run_import(settings: Settings, db: Database, ctx: JobContext) -> None:
    song_id = ctx.song_id
    if song_id is None:
        raise JobError("invalid_job", "Job di importazione senza brano.")
    storage = Storage(settings.data_dir)
    tools = MediaTools.from_settings(settings)
    spans = _SPANS_URL if ctx.kind == IMPORT_URL else _SPANS_FILE

    def report(phase: str, fraction: float, eta_s: float | None = None) -> None:
        start, end = spans[phase]
        ctx.progress(start + (end - start) * fraction, eta_s=eta_s)

    if ctx.kind == IMPORT_URL:
        ctx.stage(JobStatus.DOWNLOADING, "download", "Download dell'audio da YouTube")
        ctx.run_phase(
            "download",
            lambda: _download(settings, db, storage, ctx, partial(report, "download")),
        )

    ctx.stage(JobStatus.ANALYZING, "probe", "Verifica dell'audio")
    probe: dict[str, Any] = ctx.run_phase(
        "probe", lambda: _probe(db, storage, tools, song_id, downloaded=ctx.kind == IMPORT_URL)
    )
    report("probe", 1.0)

    ctx.stage(JobStatus.ANALYZING, "normalize", "Conversione in FLAC 44,1 kHz")
    ctx.run_phase(
        "normalize",
        lambda: _normalize(db, storage, tools, ctx, song_id, probe, partial(report, "normalize")),
    )

    ctx.stage(JobStatus.ANALYZING, "finalize", "Ultimi controlli")
    with db.session() as s:
        song = s.get(Song, song_id)
        if song is None:
            raise JobError("song_not_found", "Il brano è stato eliminato durante l'importazione.")
        song.duration_s = probe.get("duration_s") or song.duration_s
        song.status = SongStatus.READY
    report("finalize", 1.0)


# ----------------------------------------------------------------------- fasi


def _original(db: Database, song_id: str) -> AudioAsset | None:
    with db.read_session() as s:
        return s.scalars(
            select(AudioAsset).where(
                AudioAsset.song_id == song_id, AudioAsset.kind == AssetKind.ORIGINAL
            )
        ).first()


def _download(
    settings: Settings,
    db: Database,
    storage: Storage,
    ctx: JobContext,
    on_progress: Callable[[float], None],
) -> dict[str, Any]:
    song_id = ctx.song_id
    assert song_id is not None
    existing = _original(db, song_id)
    if existing is not None:  # nuovo tentativo: l'audio era già stato scaricato
        return {"path": existing.path}
    url = str(ctx.payload.get("url", ""))
    adapter = YouTubeAdapter(settings)
    try:
        path = adapter.download(url, storage.song_audio_dir(song_id), on_progress, ctx.check)
    except AppError:
        ctx.check(force=True)  # yt-dlp può aver trasformato l'annullamento in un errore
        raise
    checksum = sha256_file(path)
    duplicate = SongService(db, storage, JobQueue(db)).find_by_checksum(checksum)
    if duplicate is not None and duplicate.id != song_id:
        path.unlink(missing_ok=True)
        raise JobError(
            "duplicate_song",
            f"Questo audio è già nel catalogo: «{duplicate.title}».",
            {"song_id": duplicate.id},
        )
    with db.session() as s:
        s.add(
            AudioAsset(
                song_id=song_id,
                kind=AssetKind.ORIGINAL,
                path=storage.to_relative(path),
                format=path.suffix.lstrip(".").lower(),
                size_bytes=path.stat().st_size,
                checksum_sha256=checksum,
            )
        )
    return {"path": storage.to_relative(path)}


def _probe(
    db: Database, storage: Storage, tools: MediaTools, song_id: str, *, downloaded: bool
) -> dict[str, Any]:
    original = _original(db, song_id)
    if original is None:
        raise JobError("source_missing", "Il file originale del brano non è più disponibile.")
    path = storage.to_absolute(original.path)
    if not path.is_file():
        raise JobError("source_missing", "Il file originale del brano non è più disponibile.")
    probe = tools.probe(path)
    check_probe(probe, downloaded=downloaded)
    with db.session() as s:
        asset = s.get(AudioAsset, original.id)
        if asset is not None and probe.audio is not None:
            asset.duration_s = probe.duration_s
            asset.sample_rate = probe.audio.sample_rate
            asset.channels = probe.audio.channels
    return {**probe.to_dict(), "path": original.path}


def _normalize(
    db: Database,
    storage: Storage,
    tools: MediaTools,
    ctx: JobContext,
    song_id: str,
    probe: dict[str, Any],
    on_progress: Callable[[float, float | None], None],
) -> dict[str, Any]:
    src = storage.to_absolute(str(probe["path"]))
    dst = storage.song_audio_dir(song_id) / NORMALIZED_NAME
    duration = probe.get("duration_s")
    started = time.monotonic()

    def progress(fraction: float, speed: float | None) -> None:
        eta = None
        if duration and speed and speed > 0:
            eta = max(duration * (1.0 - fraction) / speed, 0.0)
        on_progress(fraction, eta)

    result = tools.transcode_to_flac(
        src, dst, duration_s=duration, on_progress=progress, should_stop=ctx.check
    )
    try:
        check_not_silent(result.max_volume_db)
    except AppError:
        dst.unlink(missing_ok=True)
        raise
    normalized_probe: ProbeResult = tools.probe(dst)
    elapsed = time.monotonic() - started
    with db.session() as s:
        s.execute(
            delete(AudioAsset).where(
                AudioAsset.song_id == song_id, AudioAsset.kind == AssetKind.NORMALIZED
            )
        )
        s.add(
            AudioAsset(
                song_id=song_id,
                kind=AssetKind.NORMALIZED,
                path=storage.to_relative(dst),
                format="flac",
                duration_s=normalized_probe.duration_s,
                sample_rate=normalized_probe.audio.sample_rate if normalized_probe.audio else None,
                channels=normalized_probe.audio.channels if normalized_probe.audio else None,
                size_bytes=dst.stat().st_size,
                checksum_sha256=sha256_file(dst),
            )
        )
        if duration:
            s.add(
                TimingSample(
                    phase="normalize",
                    device="cpu",
                    model="ffmpeg-flac",
                    audio_duration_s=float(duration),
                    elapsed_s=elapsed,
                )
            )
    log.info(
        "audio normalizzato",
        extra={
            "song_id": song_id,
            "elapsed_s": round(elapsed, 2),
            "max_volume_db": result.max_volume_db,
        },
    )
    return {"path": storage.to_relative(dst), "max_volume_db": result.max_volume_db}
