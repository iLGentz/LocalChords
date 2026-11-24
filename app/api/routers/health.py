from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter

from app import __version__
from app.api.deps import DatabaseDep, QueueDep, SettingsDep
from app.api.schemas import DatabaseHealth, FfmpegHealth, HealthOut, WorkerHealth
from app.db.base import utcnow
from app.db.migrate import current_revision, head_revision

router = APIRouter(tags=["system"])
log = logging.getLogger(__name__)


@router.get("/health", response_model=HealthOut)
def health(settings: SettingsDep, db: DatabaseDep, queue: QueueDep) -> HealthOut:
    head = head_revision()
    try:
        revision = current_revision(db.engine)
        last_hb = queue.last_heartbeat()
        db_ok = revision == head
    except Exception:
        log.exception("database non raggiungibile")
        revision, last_hb, db_ok = None, None, False

    alive = last_hb is not None and utcnow() - last_hb <= timedelta(
        seconds=settings.worker_stale_after_s
    )
    ffmpeg = settings.resolve_ffmpeg()
    return HealthOut(
        status="ok" if db_ok and alive else "degraded",
        version=__version__,
        database=DatabaseHealth(ok=db_ok, revision=revision, head=head),
        worker=WorkerHealth(alive=alive, last_heartbeat=last_hb),
        ffmpeg=FfmpegHealth(available=ffmpeg is not None, path=str(ffmpeg) if ffmpeg else None),
        youtube_enabled=settings.youtube_enabled,
        lrclib_enabled=settings.lrclib_enabled,
    )
