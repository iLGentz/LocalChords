"""Job ``lyrics`` (stato ``aligning``): testo sincronizzato parola per parola.

Fasi (con checkpoint):
    reference   testo di riferimento: incollato dall'utente, oppure da LRCLIB (se attivo)
    transcribe  Whisper sullo stem della voce (o sul mix), se il modello è scaricato
    align       riferimento + trascrizione → parole temporizzate; senza riferimento la
                trascrizione diventa il testo
    save        sostituisce righe e parole del brano

Parte dopo l'analisi se il testo non è stato modificato dall'utente; si rilancia dalla
scheda del brano (nuova ricerca, testo incollato).
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from app.config import Settings
from app.db.models import (
    AssetKind,
    AudioAsset,
    JobStatus,
    LyricLine,
    LyricsSource,
    LyricWord,
    Origin,
    Song,
    Stem,
    StemStatus,
    StemType,
    TimingSample,
)
from app.db.session import Database
from app.editing.history import forget
from app.errors import AppError
from app.hardware import Device, Profile, detect
from app.lyrics import lrclib
from app.lyrics.align import AsrWord, LineOut, align_lines, lines_from_transcription
from app.lyrics.models import (
    DEFAULT_RATIOS,
    WhisperSpec,
    compute_type,
    whisper_dir,
    whisper_for_profile,
    whisper_installed,
)
from app.preferences import load as load_prefs
from app.separation.runner import run_child
from app.storage.files import Storage
from app.worker.context import JobContext, JobError
from app.worker.registry import HandlerRegistry

log = logging.getLogger(__name__)

LYRICS = "lyrics"
LYRIC_TYPES = ("lyric_line", "lyric_word")
POSITION_STEP = 1024
MIN_WORDS_FOR_VOICE = 3


@dataclass(frozen=True)
class WhisperPlan:
    model: WhisperSpec
    device: Device
    installed: bool
    eta_s: float | None


def register(registry: HandlerRegistry, settings: Settings, db: Database) -> None:
    registry.register(LYRICS, JobStatus.ALIGNING, partial(run_lyrics, settings, db))


def plan_whisper(settings: Settings, db: Database, duration_s: float | None) -> WhisperPlan:
    prefs = load_prefs(db, settings)
    hw = detect()
    available = {p.id for p in hw.profiles if p.available}
    profile = hw.recommended if prefs.profile == "auto" else Profile(prefs.profile)
    if profile not in available:
        profile = Profile.LIGHT
    device = Device.CPU if prefs.device.value == "cpu" or not hw.cuda_ready else Device.CUDA
    spec = whisper_for_profile(profile)
    ratio = _ratio(db, spec.id, device)
    return WhisperPlan(
        spec,
        device,
        whisper_installed(spec, settings.data_dir),
        ratio * duration_s if duration_s else None,
    )


def _ratio(db: Database, model_id: str, device: Device) -> float:
    with db.read_session() as s:
        rows = list(
            s.execute(
                select(TimingSample.elapsed_s, TimingSample.audio_duration_s)
                .where(
                    TimingSample.phase == "transcribe",
                    TimingSample.device == device.value,
                    TimingSample.model == model_id,
                )
                .order_by(TimingSample.id.desc())
                .limit(10)
            )
        )
    values = [e / d for e, d in rows if d > 0]
    return sum(values) / len(values) if values else DEFAULT_RATIOS.get((model_id, device), 0.5)


def run_lyrics(settings: Settings, db: Database, ctx: JobContext) -> None:
    song_id = ctx.song_id
    if song_id is None:
        raise JobError("invalid_job", "Job dei testi senza brano.")
    storage = Storage(settings.data_dir)
    with db.read_session() as s:
        song = s.get(Song, song_id)
        if song is None:
            raise JobError("song_not_found", "Brano non trovato.")
        title, artist, album, duration = song.title, song.artist, song.album, song.duration_s or 0.0

    ctx.stage(JobStatus.ALIGNING, "reference", "Ricerca del testo")
    reference: dict[str, Any] = ctx.run_phase(
        "reference", lambda: _reference(settings, ctx.payload, title, artist, album, duration)
    )
    ctx.progress(0.1)

    plan = plan_whisper(settings, db, duration)
    transcript: dict[str, Any]
    if reference.get("instrumental"):
        transcript = {"skipped": "instrumental", "segments": []}
    elif not plan.installed:
        transcript = {"skipped": "model_missing", "segments": [], "model_id": plan.model.id}
    else:
        ctx.stage(
            JobStatus.ALIGNING,
            "transcribe",
            f"Trascrizione della voce ({plan.model.label}, "
            f"{'GPU' if plan.device is Device.CUDA else 'CPU'})",
        )
        transcript = ctx.run_phase(
            "transcribe", lambda: _transcribe(settings, db, storage, ctx, song_id, plan, duration)
        )

    ctx.stage(JobStatus.ALIGNING, "align", "Allineamento parola per parola")
    result: dict[str, Any] = ctx.run_phase("align", lambda: _align(reference, transcript, duration))
    ctx.progress(0.95)

    ctx.stage(JobStatus.ALIGNING, "save", "Salvataggio del testo")
    ctx.run_phase("save", lambda: _save(db, song_id, result))
    ctx.progress(1.0, eta_s=0)


def _reference(
    settings: Settings,
    payload: dict[str, Any],
    title: str,
    artist: str | None,
    album: str | None,
    duration: float,
) -> dict[str, Any]:
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        parsed = lrclib.parse_lrc(text)
        synced = any(ln.start_s is not None for ln in parsed)
        lines = parsed if synced else lrclib.plain_lines(text)
        return {
            "source": LyricsSource.USER.value,
            "synced": synced,
            "instrumental": False,
            "lines": [[ln.text, ln.start_s] for ln in lines],
        }
    if not settings.lrclib_enabled or payload.get("search") is False:
        return {
            "source": None,
            "synced": False,
            "instrumental": False,
            "lines": [],
            "note": "lrclib_disabled",
        }
    try:
        found = lrclib.fetch(title, artist, album, duration or None)
    except (OSError, ValueError) as exc:
        log.warning("LRCLIB non raggiungibile", extra={"error": str(exc)})
        return {
            "source": None,
            "synced": False,
            "instrumental": False,
            "lines": [],
            "note": "lrclib_error",
        }
    if found is None:
        return {
            "source": None,
            "synced": False,
            "instrumental": False,
            "lines": [],
            "note": "not_found",
        }
    return {
        "source": LyricsSource.LRCLIB.value,
        "synced": found.synced,
        "instrumental": found.instrumental,
        "lines": [[ln.text, ln.start_s] for ln in found.lines],
    }


def _voice_source(db: Database, storage: Storage, song_id: str) -> Path:
    with db.read_session() as s:
        vocals = s.scalars(
            select(Stem).where(
                Stem.song_id == song_id,
                Stem.type == StemType.VOCALS,
                Stem.status == StemStatus.READY,
            )
        ).first()
        mix = s.scalars(
            select(AudioAsset).where(
                AudioAsset.song_id == song_id, AudioAsset.kind == AssetKind.NORMALIZED
            )
        ).first()
    for candidate in (vocals.path if vocals else None, mix.path if mix else None):
        if candidate:
            path = storage.to_absolute(candidate)
            if path.is_file():
                return path
    raise JobError("audio_missing", "Manca l'audio del brano.")


def _transcribe(
    settings: Settings,
    db: Database,
    storage: Storage,
    ctx: JobContext,
    song_id: str,
    plan: WhisperPlan,
    duration: float,
) -> dict[str, Any]:
    audio = _voice_source(db, storage, song_id)
    started = time.monotonic()

    def on_progress(fraction: float) -> None:
        elapsed = time.monotonic() - started
        eta = elapsed / fraction * (1 - fraction) if fraction > 0.05 else plan.eta_s
        ctx.progress(0.1 + 0.8 * fraction, eta_s=eta)

    result = run_child(
        [
            "transcribe",
            "--model-dir",
            str(whisper_dir(settings.data_dir, plan.model)),
            "--audio",
            str(audio),
            "--device",
            plan.device.value,
            "--compute-type",
            compute_type(plan.device),
            "--threads",
            str(settings.cpu_threads),
        ],
        cpu_only=plan.device is Device.CPU,
        on_progress=on_progress,
        should_stop=ctx.check,
        module="app.lyrics.runner",
    )
    elapsed = time.monotonic() - started
    if duration > 0:
        with db.session() as s:
            s.add(
                TimingSample(
                    phase="transcribe",
                    device=plan.device.value,
                    model=plan.model.id,
                    audio_duration_s=duration,
                    elapsed_s=elapsed,
                )
            )
    result["vocals_stem"] = audio.name.startswith("vocals")
    return result


def _align(
    reference: dict[str, Any], transcript: dict[str, Any], duration: float
) -> dict[str, Any]:
    segments: list[dict[str, Any]] = list(transcript.get("segments") or [])
    asr = [
        AsrWord(
            str(w["word"]).strip(),
            float(w["start"]),
            float(w["end"]),
            float(w.get("probability", 0.0)),
        )
        for seg in segments
        for w in seg.get("words") or []
        if str(w["word"]).strip()
    ]
    ref_lines = [(str(t), s) for t, s in reference.get("lines", []) if str(t).strip()]
    lines: list[LineOut]
    source = reference.get("source")
    if reference.get("instrumental"):
        lines, status = [], "instrumental"
    elif ref_lines:
        lines = align_lines(ref_lines, asr, duration)
        status = "aligned" if asr else ("line_synced" if reference.get("synced") else "unsynced")
    elif len(asr) >= MIN_WORDS_FOR_VOICE:
        lines, source, status = (
            lines_from_transcription(segments),
            LyricsSource.TRANSCRIPTION.value,
            "transcribed",
        )
    elif transcript.get("skipped") == "model_missing":
        lines, status = [], "model_missing"
    else:
        lines, status = [], "no_voice"
    return {
        "source": source,
        "status": status,
        "language": transcript.get("language"),
        "lines": [asdict(ln) for ln in lines],
    }


def _save(db: Database, song_id: str, result: dict[str, Any]) -> dict[str, Any]:
    with db.session() as s:
        song = s.get(Song, song_id)
        if song is None:
            raise JobError("song_not_found", "Il brano è stato eliminato.")
        line_ids = select(LyricLine.id).where(LyricLine.song_id == song_id)
        s.execute(delete(LyricWord).where(LyricWord.line_id.in_(line_ids)))
        s.execute(delete(LyricLine).where(LyricLine.song_id == song_id))
        forget(s, song_id, LYRIC_TYPES)
        # Tutto ciò che produce il job è lo stato "originale" (anche un testo incollato):
        # Origin.USER resta per le righe e parole aggiunte a mano nell'editor.
        origin = Origin.ANALYSIS
        for i, ln in enumerate(result["lines"]):
            line = LyricLine(
                song_id=song_id,
                position=(i + 1) * POSITION_STEP,
                text=ln["text"],
                start_s=ln["start_s"],
                end_s=ln["end_s"],
                original_text=ln["text"],
                original_start_s=ln["start_s"],
                original_end_s=ln["end_s"],
                origin=origin,
            )
            s.add(line)
            s.flush()
            for j, w in enumerate(ln["words"]):
                s.add(
                    LyricWord(
                        line_id=line.id,
                        position=(j + 1) * POSITION_STEP,
                        text=w["text"],
                        start_s=w["start_s"],
                        end_s=w["end_s"],
                        confidence=w["confidence"],
                        original_text=w["text"],
                        original_start_s=w["start_s"],
                        original_end_s=w["end_s"],
                        origin=origin,
                    )
                )
        song.lyrics_source = LyricsSource(result["source"]) if result["source"] else None
    return {"lines": len(result["lines"]), "status": result["status"]}


def ensure_whisper_ok(settings: Settings, db: Database) -> None:
    """Errore esplicito se non è possibile trascrivere (usato dall'API per i messaggi)."""
    plan = plan_whisper(settings, db, None)
    if not plan.installed:
        raise AppError(
            "model_missing",
            f"Per l'allineamento serve il modello {plan.model.label} (~{plan.model.size_mb} MB).",
            {"model_id": plan.model.id, "size_mb": plan.model.size_mb},
        )
