"""Job ``analyze``: waveform, beat e BPM, accordi e tonalità, sezioni; poi salvataggio.

Parte automaticamente al termine dell'importazione e si può rilanciare
(``POST /api/songs/{id}/analyze``). Rilanciarla sostituisce i risultati precedenti,
modifiche dell'utente comprese.

Le fasi di calcolo sono chiamate di libreria non interrompibili: l'annullamento ha effetto
tra una fase e l'altra (al massimo qualche decina di secondi su CPU).
"""

from __future__ import annotations

import logging
import time
from functools import partial
from pathlib import Path
from typing import Any

from sqlalchemy import delete, insert, select

from app.analysis.beats import BeatGrid, detect_beats
from app.analysis.features import Features, load_mono
from app.analysis.harmony import ChordEventData, detect_chords, detect_key
from app.analysis.harmony import to_dicts as chords_to_dicts
from app.analysis.sections import detect_sections
from app.analysis.sections import to_dicts as sections_to_dicts
from app.analysis.waveform import compute_peaks
from app.config import Settings
from app.db.models import (
    AssetKind,
    AudioAsset,
    Beat,
    ChordEvent,
    Job,
    JobStatus,
    Origin,
    Section,
    Song,
    SongStatus,
    Stem,
    StemStatus,
    StemType,
    TimingSample,
)
from app.db.session import Database
from app.editing.history import forget, has_edits
from app.importing.service import ANALYZE
from app.storage.files import Storage
from app.worker.context import JobContext, JobError
from app.worker.registry import HandlerRegistry

log = logging.getLogger(__name__)

DEVICE = "cpu"
# (fase, peso nell'avanzamento, secondi di calcolo per secondo di audio se non ci sono misure)
PHASES: tuple[tuple[str, float, float], ...] = (
    ("waveform", 0.08, 0.01),
    ("beats", 0.22, 0.06),
    ("harmony", 0.45, 0.12),
    ("sections", 0.20, 0.04),
    ("save", 0.05, 0.002),
)
HARMONIC_STEMS = (StemType.BASS, StemType.GUITAR, StemType.PIANO, StemType.OTHER)


def register(registry: HandlerRegistry, settings: Settings, db: Database) -> None:
    registry.register(ANALYZE, JobStatus.ANALYZING, partial(run_analysis, settings, db))


def waveform_path(storage: Storage, song_id: str) -> Path:
    return storage.root / "waveforms" / song_id / "peaks.json"


class _Lazy:
    """Feature calcolate una sola volta per esecuzione e condivise tra le fasi."""

    def __init__(self, mix: Path, harmonic_sources: list[Path]) -> None:
        self._mix = mix
        self._harmonic_sources = harmonic_sources
        self._full: Features | None = None
        self._harm: Features | None = None

    @property
    def full(self) -> Features:
        if self._full is None:
            self._full = Features(load_mono([self._mix]))
        return self._full

    @property
    def harmonic(self) -> Features:
        """Mix senza voce e batteria se gli stem esistono, altrimenti il mix completo."""
        if not self._harmonic_sources:
            return self.full
        if self._harm is None:
            self._harm = Features(load_mono(self._harmonic_sources))
        return self._harm


def run_analysis(settings: Settings, db: Database, ctx: JobContext) -> None:
    song_id = ctx.song_id
    if song_id is None:
        raise JobError("invalid_job", "Job di analisi senza brano.")
    storage = Storage(settings.data_dir)
    mix, duration, harmonic_sources = _sources(db, storage, song_id)
    lazy = _Lazy(mix, harmonic_sources)
    ratios = _measured_ratios(db)
    _set_song_status(db, song_id, SongStatus.PROCESSING)

    done_weight = 0.0
    for name, weight, _default in PHASES:
        remaining = sum(ratios[n] * duration for n, _w, _d in PHASES if n not in _before(name))
        ctx.stage(JobStatus.ANALYZING, name, _MESSAGES[name])
        ctx.progress(done_weight, eta_s=remaining)
        started = time.monotonic()
        result = ctx.run_phase(name, partial(_PHASE_FN[name], lazy, ctx, storage, db, song_id))
        elapsed = time.monotonic() - started
        if result is not None and elapsed > 0.05:
            _record_timing(db, name, duration, elapsed)
        done_weight += weight
    ctx.progress(1.0, eta_s=0)
    _set_song_status(db, song_id, SongStatus.READY)
    _enqueue_lyrics(db, song_id)


def _enqueue_lyrics(db: Database, song_id: str) -> None:
    """Testi dopo l'analisi, salvo che l'utente li abbia già modificati."""
    from app.lyrics.jobs import LYRIC_TYPES, LYRICS

    with db.session() as s:
        if has_edits(s, song_id, LYRIC_TYPES):
            return
        s.add(
            Job(
                kind=LYRICS,
                song_id=song_id,
                payload={"search": True},
                checkpoint={},
                message="In coda",
            )
        )


_MESSAGES = {
    "waveform": "Waveform",
    "beats": "Beat, battute e BPM",
    "harmony": "Accordi e tonalità",
    "sections": "Sezioni del brano",
    "save": "Salvataggio dei risultati",
}


def _before(name: str) -> set[str]:
    names = [n for n, _w, _d in PHASES]
    return set(names[: names.index(name)])


# --------------------------------------------------------------------- fasi


def _phase_waveform(
    lazy: _Lazy, ctx: JobContext, storage: Storage, db: Database, song_id: str
) -> dict[str, Any]:
    return dict(compute_peaks(lazy._mix, waveform_path(storage, song_id)))


def _phase_beats(
    lazy: _Lazy, ctx: JobContext, storage: Storage, db: Database, song_id: str
) -> dict[str, Any]:
    return detect_beats(lazy.full).to_dict()


def _grid(ctx: JobContext) -> BeatGrid:
    data = ctx.phase_result("beats")
    return BeatGrid(
        times=list(data["times"]),
        downbeats=list(data["downbeats"]),
        bars=list(data["bars"]),
        bpm=data["bpm"],
        bpm_confidence=float(data["bpm_confidence"]),
        beats_per_bar=int(data["beats_per_bar"]),
    )


def _phase_harmony(
    lazy: _Lazy, ctx: JobContext, storage: Storage, db: Database, song_id: str
) -> dict[str, Any]:
    grid = _grid(ctx)
    chords = detect_chords(lazy.harmonic, grid)
    ctx.check()
    key = detect_key(lazy.harmonic, chords)
    return {
        "chords": chords_to_dicts(chords),
        "key": key.key,
        "key_confidence": key.confidence,
        "stems_used": bool(lazy._harmonic_sources),
    }


def _phase_sections(
    lazy: _Lazy, ctx: JobContext, storage: Storage, db: Database, song_id: str
) -> dict[str, Any]:
    return {"sections": sections_to_dicts(detect_sections(lazy.full, _grid(ctx)))}


def _phase_save(
    lazy: _Lazy, ctx: JobContext, storage: Storage, db: Database, song_id: str
) -> dict[str, Any]:
    grid = _grid(ctx)
    harmony = ctx.phase_result("harmony")
    sections = ctx.phase_result("sections")["sections"]
    chords = [ChordEventData(**c) for c in harmony["chords"]]
    with db.session() as s:
        song = s.get(Song, song_id)
        if song is None:
            raise JobError("song_not_found", "Il brano è stato eliminato durante l'analisi.")
        for model in (Beat, ChordEvent, Section):
            s.execute(delete(model).where(model.song_id == song_id))
        forget(s, song_id, ("chord", "section"))
        if grid.times:
            s.execute(
                insert(Beat),
                [
                    {
                        "song_id": song_id,
                        "position": i,
                        "time_s": t,
                        "is_downbeat": grid.downbeats[i],
                        "bar": grid.bars[i],
                    }
                    for i, t in enumerate(grid.times)
                ],
            )
        for c in chords:
            s.add(
                ChordEvent(
                    song_id=song_id,
                    start_s=c.start_s,
                    end_s=c.end_s,
                    chord=c.chord,
                    confidence=c.confidence,
                    beat_position=c.beat_position,
                    original_start_s=c.start_s,
                    original_end_s=c.end_s,
                    original_chord=c.chord,
                    origin=Origin.ANALYSIS,
                )
            )
        for sec in sections:
            s.add(
                Section(
                    song_id=song_id,
                    name=sec["name"],
                    color=sec["color"],
                    start_s=sec["start_s"],
                    end_s=sec["end_s"],
                    original_name=sec["name"],
                    original_color=sec["color"],
                    original_start_s=sec["start_s"],
                    original_end_s=sec["end_s"],
                    origin=Origin.ANALYSIS,
                )
            )
        song.bpm = song.original_bpm = grid.bpm
        song.bpm_confidence = grid.bpm_confidence
        song.beats_per_bar = grid.beats_per_bar
        song.beat_offset_s = song.original_beat_offset_s = 0.0
        song.key = song.original_key = harmony["key"]
        song.key_confidence = harmony["key_confidence"]
    log.info(
        "analisi salvata",
        extra={
            "song_id": song_id,
            "beats": len(grid.times),
            "chords": len(chords),
            "sections": len(sections),
            "bpm": grid.bpm,
            "key": harmony["key"],
        },
    )
    return {"saved": True}


_PHASE_FN = {
    "waveform": _phase_waveform,
    "beats": _phase_beats,
    "harmony": _phase_harmony,
    "sections": _phase_sections,
    "save": _phase_save,
}


# ---------------------------------------------------------------- supporto


def _sources(db: Database, storage: Storage, song_id: str) -> tuple[Path, float, list[Path]]:
    with db.read_session() as s:
        asset = s.scalars(
            select(AudioAsset).where(
                AudioAsset.song_id == song_id, AudioAsset.kind == AssetKind.NORMALIZED
            )
        ).first()
        stems = list(
            s.scalars(
                select(Stem).where(
                    Stem.song_id == song_id,
                    Stem.status == StemStatus.READY,
                    Stem.type.in_(HARMONIC_STEMS),
                )
            )
        )
    if asset is None:
        raise JobError("audio_missing", "Manca l'audio normalizzato: reimporta il brano.")
    mix = storage.to_absolute(asset.path)
    if not mix.is_file():
        raise JobError("audio_missing", "Il file audio del brano non è più disponibile.")
    harmonic: list[Path] = []
    if len(stems) == len(HARMONIC_STEMS):
        harmonic = [storage.to_absolute(st.path) for st in stems if st.path]
        if not all(p.is_file() for p in harmonic) or len(harmonic) != len(HARMONIC_STEMS):
            harmonic = []
    return mix, float(asset.duration_s or 0.0), harmonic


def _measured_ratios(db: Database) -> dict[str, float]:
    """Secondi di calcolo per secondo di audio: media delle ultime misure, se ce ne sono."""
    ratios = {name: default for name, _w, default in PHASES}
    with db.read_session() as s:
        for name in ratios:
            rows = list(
                s.execute(
                    select(TimingSample.elapsed_s, TimingSample.audio_duration_s)
                    .where(TimingSample.phase == f"analysis.{name}", TimingSample.device == DEVICE)
                    .order_by(TimingSample.id.desc())
                    .limit(10)
                )
            )
            values = [e / d for e, d in rows if d > 0]
            if values:
                ratios[name] = sum(values) / len(values)
    return ratios


def _record_timing(db: Database, phase: str, duration: float, elapsed: float) -> None:
    if duration <= 0:
        return
    with db.session() as s:
        s.add(
            TimingSample(
                phase=f"analysis.{phase}",
                device=DEVICE,
                model="librosa",
                audio_duration_s=duration,
                elapsed_s=elapsed,
            )
        )


def _set_song_status(db: Database, song_id: str, status: SongStatus) -> None:
    with db.session() as s:
        song = s.get(Song, song_id)
        if song is not None:
            song.status = status
