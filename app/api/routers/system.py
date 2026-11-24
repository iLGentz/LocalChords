"""Sistema: hardware e profili, preferenze di elaborazione, modelli, spazio su disco."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.api.deps import DatabaseDep, QueueDep, SettingsDep, SongsDep, StorageDep
from app.api.schemas import JobOut
from app.db.models import Job, JobStatus, Song, StemType
from app.errors import AppError
from app.hardware import detect
from app.importing.service import ACTIVE_JOB_STATUSES, DOWNLOAD_MODEL
from app.preferences import ProcessingPreferences
from app.preferences import load as load_prefs
from app.preferences import save as save_prefs
from app.separation.jobs import measured_ratio, runtime_installed
from app.separation.models import MODELS, is_installed, models_dir, size_on_disk
from app.storage import usage

router = APIRouter(tags=["system"])

REFERENCE_SONG_S = 240.0  # stime mostrate per un brano di 4 minuti


# ------------------------------------------------------------------ hardware


class EstimateOut(BaseModel):
    profile: str
    device: str
    model: str
    seconds_for_4min: float


class HardwareOut(BaseModel):
    info: dict[str, object]
    installed_runtime: str
    separation_runtime: bool
    preferences: ProcessingPreferences
    estimates: list[EstimateOut]


@router.get("/system/hardware", response_model=HardwareOut)
async def hardware(
    settings: SettingsDep,
    db: DatabaseDep,
    refresh: Annotated[bool, Query()] = False,
) -> HardwareOut:
    info = await run_in_threadpool(detect, refresh)
    estimates = []
    for p in info.profiles:
        if p.available:
            model = MODELS[p.separation_model]
            ratio = measured_ratio(db, model.id, p.device)
            estimates.append(
                EstimateOut(
                    profile=p.id.value,
                    device=p.device.value,
                    model=model.id,
                    seconds_for_4min=round(ratio * REFERENCE_SONG_S, 1),
                )
            )
    return HardwareOut(
        info=info.to_dict(),
        installed_runtime=settings.installed_runtime.value,
        separation_runtime=runtime_installed(),
        preferences=load_prefs(db, settings),
        estimates=estimates,
    )


@router.get("/settings/processing", response_model=ProcessingPreferences)
def get_processing(settings: SettingsDep, db: DatabaseDep) -> ProcessingPreferences:
    return load_prefs(db, settings)


@router.put("/settings/processing", response_model=ProcessingPreferences)
def put_processing(body: ProcessingPreferences, db: DatabaseDep) -> ProcessingPreferences:
    return save_prefs(db, body)


# -------------------------------------------------------------------- modelli


class ModelOut(BaseModel):
    id: str
    label: str
    description: str
    size_mb: int
    license: str
    commercial_use: bool
    profiles: list[str]
    installed: bool
    size_on_disk: int
    download_job: JobOut | None


def _download_jobs(db: DatabaseDep) -> dict[str, Job]:
    with db.read_session() as s:
        jobs = s.scalars(
            select(Job).where(Job.kind == DOWNLOAD_MODEL, Job.status.in_(ACTIVE_JOB_STATUSES))
        )
        return {str(j.payload.get("model_id")): j for j in jobs}


@router.get("/models", response_model=list[ModelOut])
def list_models(settings: SettingsDep, db: DatabaseDep) -> list[ModelOut]:
    active = _download_jobs(db)
    return [
        ModelOut(
            id=m.id,
            label=m.label,
            description=m.description,
            size_mb=m.size_mb,
            license=m.license,
            commercial_use=m.commercial_use,
            profiles=[p.value for p in m.profiles],
            installed=is_installed(m, settings.data_dir),
            size_on_disk=size_on_disk(m, settings.data_dir),
            download_job=JobOut.from_job(active[m.id]) if m.id in active else None,
        )
        for m in MODELS.values()
    ]


@router.post("/models/{model_id}/download", response_model=JobOut, status_code=202)
def download_model(
    model_id: str, settings: SettingsDep, db: DatabaseDep, queue: QueueDep
) -> JobOut:
    spec = MODELS.get(model_id)
    if spec is None:
        raise AppError("model_not_found", "Modello sconosciuto.")
    if not runtime_installed():
        raise AppError(
            "separation_runtime_missing",
            "Il runtime di separazione non è installato: riesegui setup.ps1.",
        )
    existing = _download_jobs(db).get(model_id)
    job_id = existing.id if existing else queue.enqueue(DOWNLOAD_MODEL, {"model_id": model_id})
    job = queue.get(job_id)
    assert job is not None
    return JobOut.from_job(job)


@router.delete("/models/{model_id}", status_code=204)
def delete_model(model_id: str, settings: SettingsDep, db: DatabaseDep) -> Response:
    spec = MODELS.get(model_id)
    if spec is None:
        raise AppError("model_not_found", "Modello sconosciuto.")
    with db.read_session() as s:
        busy = s.scalars(
            select(Job).where(
                Job.kind.in_(("separate", DOWNLOAD_MODEL)),
                Job.status.in_(ACTIVE_JOB_STATUSES - {JobStatus.QUEUED}),
            )
        ).first()
    if busy is not None:
        raise AppError("model_busy", "Una separazione o un download è in corso: riprova dopo.")
    directory = models_dir(settings.data_dir)
    for name in spec.files:
        (directory / name).unlink(missing_ok=True)
    return Response(status_code=204)


# ---------------------------------------------------------------------- spazio


class SongUsageOut(BaseModel):
    song_id: str
    title: str
    artist: str | None
    audio: int
    stems: int
    waveforms: int
    total: int


class StorageOut(BaseModel):
    data_dir: str
    categories: dict[str, int]
    total: int
    disk_free: int
    disk_total: int
    songs: list[SongUsageOut]
    cleanable: list[str]


@router.get("/system/storage", response_model=StorageOut)
async def storage_usage(settings: SettingsDep, storage: StorageDep, db: DatabaseDep) -> StorageOut:
    def compute() -> StorageOut:
        with db.read_session() as s:
            songs = {sg.id: sg for sg in s.scalars(select(Song))}
        categories = usage.category_sizes(storage, settings.database_path)
        per_song = sorted(usage.song_usage(storage, list(songs)), key=lambda u: -u.total)
        free, total = usage.disk_free(storage.root)
        return StorageOut(
            data_dir=str(storage.root),
            categories=categories,
            total=sum(categories.values()),
            disk_free=free,
            disk_total=total,
            songs=[
                SongUsageOut(
                    song_id=u.song_id,
                    title=songs[u.song_id].title,
                    artist=songs[u.song_id].artist,
                    audio=u.audio,
                    stems=u.stems,
                    waveforms=u.waveforms,
                    total=u.total,
                )
                for u in per_song
            ],
            cleanable=list(usage.CLEANABLE),
        )

    return await run_in_threadpool(compute)


class CleanupIn(BaseModel):
    targets: list[Literal["cache", "uploads", "exports"]]


class CleanupOut(BaseModel):
    freed_bytes: int


@router.post("/system/storage/cleanup", response_model=CleanupOut)
def storage_cleanup(body: CleanupIn, storage: StorageDep) -> CleanupOut:
    return CleanupOut(freed_bytes=usage.cleanup(storage, list(body.targets)))


# ----------------------------------------------------------------- stem brano


class StemOut(BaseModel):
    type: str
    status: str
    model: str | None
    size_bytes: int | None
    url: str


class SeparationPlanOut(BaseModel):
    model_id: str
    model_label: str
    model_size_mb: int
    model_installed: bool
    model_license: str
    device: str
    profile: str
    eta_s: float | None
    note: str | None


class SeparateIn(BaseModel):
    device: Literal["auto", "nvidia", "cpu"] | None = None
    profile: Literal["auto", "light", "balanced", "max"] | None = None
    allow_download: bool = False


@router.get("/songs/{song_id}/stems", response_model=list[StemOut])
def list_stems(song_id: str, songs: SongsDep, db: DatabaseDep) -> list[StemOut]:
    from app.db.models import Stem

    songs.get(song_id)
    with db.read_session() as s:
        rows = list(s.scalars(select(Stem).where(Stem.song_id == song_id)))
    order = ["vocals", "drums", "bass", "guitar", "piano", "other"]
    rows.sort(key=lambda r: order.index(r.type.value))
    return [
        StemOut(
            type=r.type.value,
            status=r.status.value,
            model=r.model,
            size_bytes=r.size_bytes,
            url=f"/api/songs/{song_id}/stems/{r.type.value}/audio",
        )
        for r in rows
    ]


@router.get("/songs/{song_id}/separation-plan", response_model=SeparationPlanOut)
async def separation_plan(
    song_id: str,
    settings: SettingsDep,
    db: DatabaseDep,
    songs: SongsDep,
    device: Annotated[Literal["auto", "nvidia", "cpu"] | None, Query()] = None,
    profile: Annotated[Literal["auto", "light", "balanced", "max"] | None, Query()] = None,
) -> SeparationPlanOut:
    from app.separation.jobs import plan_separation

    song = songs.get(song_id)
    plan = await run_in_threadpool(
        lambda: plan_separation(settings, db, song.duration_s, device=device, profile=profile)
    )
    return SeparationPlanOut(
        model_id=plan.model.id,
        model_label=plan.model.label,
        model_size_mb=plan.model.size_mb,
        model_installed=plan.model_installed,
        model_license=plan.model.license,
        device=plan.device.value,
        profile=plan.profile.value,
        eta_s=plan.eta_s,
        note=plan.note,
    )


@router.post("/songs/{song_id}/separate", response_model=JobOut, status_code=202)
def separate(song_id: str, body: SeparateIn, songs: SongsDep, queue: QueueDep) -> JobOut:
    payload: dict[str, object] = {"allow_download": body.allow_download, "reanalyze": True}
    if body.device:
        payload["device"] = body.device
    if body.profile:
        payload["profile"] = body.profile
    job = queue.get(songs.separate(song_id, payload))
    assert job is not None
    return JobOut.from_job(job)


@router.delete("/songs/{song_id}/stems", response_model=CleanupOut)
def delete_stems(song_id: str, songs: SongsDep) -> CleanupOut:
    return CleanupOut(freed_bytes=songs.delete_stems(song_id))


@router.get("/songs/{song_id}/stems/{stem_type}/audio", response_class=FileResponse)
def stem_audio(
    song_id: str, stem_type: str, songs: SongsDep, db: DatabaseDep, storage: StorageDep
) -> FileResponse:
    from app.db.models import Stem

    songs.get(song_id)
    with db.read_session() as s:
        row = (
            s.scalars(select(Stem).where(Stem.song_id == song_id, Stem.type == stem_type)).first()
            if stem_type in {t.value for t in StemType}
            else None
        )
    path = storage.to_absolute(row.path) if row is not None and row.path else None
    if path is None or not path.is_file():
        raise AppError("stem_not_found", "Stem non disponibile.")
    return FileResponse(path, media_type="audio/flac")
