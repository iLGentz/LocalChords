"""Job ``separate`` (6 stem) e ``download_model``.

Separazione, fasi con checkpoint:
    model     scarica il modello se manca (solo se l'utente l'ha confermato)
    separate  esegue audio-separator in un processo figlio terminabile
    save      sposta gli stem in data/stems/<id>/<tipo>.flac, li registra e
              accoda la nuova analisi (gli accordi useranno il mix senza voce e batteria)
"""

from __future__ import annotations

import importlib.util
import logging
import shutil
import time
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from app.config import Settings
from app.db.models import (
    AssetKind,
    AudioAsset,
    Job,
    JobStatus,
    Song,
    SongStatus,
    Stem,
    StemStatus,
    StemType,
    TimingSample,
)
from app.db.session import Database
from app.errors import AppError
from app.hardware import Device, Profile, detect
from app.importing.service import ANALYZE, DOWNLOAD_MODEL, SEPARATE
from app.preferences import load as load_prefs
from app.separation.models import (
    DEFAULT_RATIOS,
    MODELS,
    ModelSpec,
    is_installed,
    model_for_profile,
    models_dir,
)
from app.separation.runner import run_child
from app.storage.files import Storage, remove_tree
from app.worker.context import JobContext, JobError
from app.worker.registry import HandlerRegistry

log = logging.getLogger(__name__)

_STEM_MARKERS = {t: f"({t.value})" for t in StemType}


@dataclass(frozen=True)
class SeparationPlan:
    model: ModelSpec
    device: Device
    profile: Profile
    model_installed: bool
    eta_s: float | None
    note: str | None


def runtime_installed() -> bool:
    return importlib.util.find_spec("audio_separator") is not None


def plan_separation(
    settings: Settings,
    db: Database,
    duration_s: float | None,
    *,
    device: str | None = None,
    profile: str | None = None,
) -> SeparationPlan:
    """Sceglie modello e dispositivo da preferenze, hardware ed eventuali scelte del job."""
    if not runtime_installed():
        raise AppError(
            "separation_runtime_missing",
            "Il runtime di separazione non è installato: riesegui setup.ps1.",
        )
    prefs = load_prefs(db, settings)
    hw = detect()
    available = {p.id: p for p in hw.profiles if p.available}
    wanted = profile or prefs.profile
    chosen = hw.recommended if wanted == "auto" else Profile(wanted)
    note = None
    if chosen not in available:
        if Profile.LIGHT not in available:
            raise AppError("separation_unavailable", "Nessun profilo di separazione disponibile.")
        note = f"Profilo «{chosen.value}» non disponibile su questo PC: uso il profilo Leggero."
        chosen = Profile.LIGHT

    wanted_device = device or prefs.device.value
    if wanted_device == "nvidia":
        if not hw.cuda_ready:
            raise AppError(
                "gpu_unavailable",
                "GPU NVIDIA non disponibile: controlla il driver o scegli Solo CPU.",
            )
        resolved = Device.CUDA
    elif wanted_device == "cpu":
        resolved = Device.CPU
    else:
        resolved = Device.CUDA if hw.cuda_ready else Device.CPU

    model = model_for_profile(chosen)
    ratio = measured_ratio(db, model.id, resolved)
    return SeparationPlan(
        model=model,
        device=resolved,
        profile=chosen,
        model_installed=is_installed(model, settings.data_dir),
        eta_s=ratio * duration_s if duration_s else None,
        note=note,
    )


def measured_ratio(db: Database, model_id: str, device: Device) -> float:
    with db.read_session() as s:
        rows = list(
            s.execute(
                select(TimingSample.elapsed_s, TimingSample.audio_duration_s)
                .where(
                    TimingSample.phase == "separate",
                    TimingSample.device == device.value,
                    TimingSample.model == model_id,
                )
                .order_by(TimingSample.id.desc())
                .limit(10)
            )
        )
    values = [e / d for e, d in rows if d > 0]
    if values:
        return sum(values) / len(values)
    return DEFAULT_RATIOS.get((model_id, device), 1.0)


def register(registry: HandlerRegistry, settings: Settings, db: Database) -> None:
    registry.register(SEPARATE, JobStatus.SEPARATING, partial(run_separation, settings, db))
    registry.register(DOWNLOAD_MODEL, JobStatus.DOWNLOADING, partial(run_download, settings, db))


# ------------------------------------------------------------------ download


def _download(
    settings: Settings, ctx: JobContext, spec: ModelSpec, span: tuple[float, float]
) -> None:
    start, end = span
    run_child(
        [
            "download",
            "--model-file",
            spec.filename,
            "--model-dir",
            str(models_dir(settings.data_dir)),
        ],
        cpu_only=True,
        on_progress=lambda f: ctx.progress(start + (end - start) * f),
        should_stop=ctx.check,
    )
    if not is_installed(spec, settings.data_dir):
        raise JobError("model_download_failed", f"Download del modello {spec.label} incompleto.")


def run_download(settings: Settings, db: Database, ctx: JobContext) -> None:
    spec = MODELS.get(str(ctx.payload.get("model_id")))
    if spec is None:
        raise JobError("model_not_found", "Modello sconosciuto.")
    if is_installed(spec, settings.data_dir):
        return
    ctx.stage(JobStatus.DOWNLOADING, "download", f"Download di {spec.label} (~{spec.size_mb} MB)")
    _download(settings, ctx, spec, (0.0, 1.0))


# ---------------------------------------------------------------- separazione


def run_separation(settings: Settings, db: Database, ctx: JobContext) -> None:
    song_id = ctx.song_id
    if song_id is None:
        raise JobError("invalid_job", "Job di separazione senza brano.")
    storage = Storage(settings.data_dir)
    mix, duration = _mix(db, storage, song_id)
    _set_status(db, song_id, SongStatus.PROCESSING)

    plan_data: dict[str, Any] = ctx.run_phase(
        "plan",
        lambda: _plan_dict(settings, db, duration, ctx.payload),
    )
    spec = MODELS[plan_data["model_id"]]
    device = Device(plan_data["device"])

    ctx.stage(JobStatus.SEPARATING, "model", f"Modello {spec.label}")
    if not is_installed(spec, settings.data_dir):
        if not ctx.payload.get("allow_download"):
            raise JobError(
                "model_missing",
                f"Il modello {spec.label} (~{spec.size_mb} MB) non è scaricato.",
                {"model_id": spec.id, "size_mb": spec.size_mb},
            )
        ctx.stage(JobStatus.DOWNLOADING, "model", f"Download di {spec.label} (~{spec.size_mb} MB)")
        _download(settings, ctx, spec, (0.0, 0.2))

    work = storage.root / "stems" / song_id / "_work"
    eta = plan_data.get("eta_s")
    ctx.stage(
        JobStatus.SEPARATING,
        "separate",
        f"Separazione in 6 stem con {spec.label} ({'GPU' if device is Device.CUDA else 'CPU'})",
    )
    outputs: dict[str, Any] = ctx.run_phase(
        "separate",
        lambda: _separate(settings, ctx, spec, device, mix, work, eta),
    )

    ctx.stage(JobStatus.SEPARATING, "save", "Salvataggio degli stem")
    ctx.run_phase("save", lambda: _save(db, storage, song_id, spec, outputs, work))
    _record_timing(db, spec.id, device, duration, float(outputs["elapsed_s"]))

    if ctx.payload.get("reanalyze", True):
        with db.session() as s:
            s.add(Job(kind=ANALYZE, song_id=song_id, payload={}, checkpoint={}, message="In coda"))
    else:
        _set_status(db, song_id, SongStatus.READY)
    ctx.progress(1.0, eta_s=0)


def _plan_dict(
    settings: Settings, db: Database, duration: float, payload: dict[str, Any]
) -> dict[str, Any]:
    plan = plan_separation(
        settings,
        db,
        duration,
        device=payload.get("device"),
        profile=payload.get("profile"),
    )
    return {"model_id": plan.model.id, "device": plan.device.value, "eta_s": plan.eta_s}


def _separate(
    settings: Settings,
    ctx: JobContext,
    spec: ModelSpec,
    device: Device,
    mix: Path,
    work: Path,
    eta: float | None,
) -> dict[str, Any]:
    remove_tree(work)
    work.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    seen_real = {"value": False}

    def on_progress(fraction: float) -> None:
        seen_real["value"] = True
        elapsed = time.monotonic() - started
        remaining = elapsed / fraction * (1 - fraction) if fraction > 0.02 else eta
        ctx.progress(0.2 + 0.75 * fraction, eta_s=remaining)

    def tick() -> None:
        ctx.check()
        if not seen_real["value"] and eta:
            elapsed = time.monotonic() - started
            ctx.progress(0.2 + 0.75 * min(elapsed / eta, 0.95), eta_s=max(eta - elapsed, 0))

    result = run_child(
        [
            "separate",
            "--model-file",
            spec.filename,
            "--model-dir",
            str(models_dir(settings.data_dir)),
            "--input",
            str(mix),
            "--output-dir",
            str(work),
        ],
        cpu_only=device is Device.CPU,
        on_progress=on_progress,
        should_stop=tick,
        cpu_threads=settings.cpu_threads,
    )
    if device is Device.CUDA and not result.get("cuda"):
        log.warning("separazione richiesta su GPU ma eseguita su CPU")
    files: dict[str, str] = {}
    for name in result.get("files", []):
        lower = Path(name).name.lower()
        for stem_type, marker in _STEM_MARKERS.items():
            if marker in lower:
                files[stem_type.value] = str(name)
    missing = [t.value for t in StemType if t.value not in files]
    if missing:
        raise JobError(
            "separation_incomplete",
            f"Il modello non ha prodotto tutti gli stem (mancano: {', '.join(missing)}).",
        )
    return {"files": files, "elapsed_s": time.monotonic() - started}


def _save(
    db: Database,
    storage: Storage,
    song_id: str,
    spec: ModelSpec,
    outputs: dict[str, Any],
    work: Path,
) -> dict[str, Any]:
    target = storage.root / "stems" / song_id
    rows: list[Stem] = []
    for stem_type in StemType:
        src = Path(outputs["files"][stem_type.value])
        dst = target / f"{stem_type.value}.flac"
        if src.is_file():
            shutil.move(str(src), dst)
        if not dst.is_file():
            raise JobError("separation_incomplete", f"Stem mancante: {stem_type.value}")
        rows.append(
            Stem(
                song_id=song_id,
                type=stem_type,
                path=storage.to_relative(dst),
                format="flac",
                status=StemStatus.READY,
                model=spec.id,
                size_bytes=dst.stat().st_size,
            )
        )
    with db.session() as s:
        if s.get(Song, song_id) is None:
            raise JobError("song_not_found", "Il brano è stato eliminato durante la separazione.")
        s.execute(delete(Stem).where(Stem.song_id == song_id))
        s.add_all(rows)
    remove_tree(work)
    return {"saved": len(rows)}


def _mix(db: Database, storage: Storage, song_id: str) -> tuple[Path, float]:
    with db.read_session() as s:
        asset = s.scalars(
            select(AudioAsset).where(
                AudioAsset.song_id == song_id, AudioAsset.kind == AssetKind.NORMALIZED
            )
        ).first()
    if asset is None:
        raise JobError("audio_missing", "Manca l'audio normalizzato: reimporta il brano.")
    path = storage.to_absolute(asset.path)
    if not path.is_file():
        raise JobError("audio_missing", "Il file audio del brano non è più disponibile.")
    return path, float(asset.duration_s or 0.0)


def _record_timing(
    db: Database, model_id: str, device: Device, duration: float, elapsed: float
) -> None:
    if duration <= 0 or elapsed <= 0:
        return
    with db.session() as s:
        s.add(
            TimingSample(
                phase="separate",
                device=device.value,
                model=model_id,
                audio_duration_s=duration,
                elapsed_s=elapsed,
            )
        )


def _set_status(db: Database, song_id: str, status: SongStatus) -> None:
    with db.session() as s:
        song = s.get(Song, song_id)
        if song is not None:
            song.status = status
