"""Job ``tabs``: note di chitarra e basso dagli stem, con corda e tasto.

Richiede gli stem (chitarra e/o basso). Fasi: modello (scaricato su richiesta, 700 KB),
una fase per strumento (inferenza + diteggiatura), salvataggio.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from functools import partial
from typing import Any

from sqlalchemy import delete, select

from app.config import Settings
from app.db.models import Instrument, JobStatus, Song, Stem, StemStatus, StemType, TabNote
from app.db.session import Database
from app.storage.files import Storage
from app.tabs.basic_pitch import BasicPitch, ensure_model, load_audio, notes_from_output
from app.tabs.fretting import BASS_TUNING, GUITAR_TUNING, FrettedNote, assign, playable_range
from app.worker.context import JobContext, JobError
from app.worker.registry import HandlerRegistry

log = logging.getLogger(__name__)

TABS = "tabs"
INSTRUMENTS: dict[Instrument, tuple[StemType, tuple[int, ...]]] = {
    Instrument.GUITAR: (StemType.GUITAR, GUITAR_TUNING),
    Instrument.BASS: (StemType.BASS, BASS_TUNING),
}


def register(registry: HandlerRegistry, settings: Settings, db: Database) -> None:
    registry.register(TABS, JobStatus.ANALYZING, partial(run_tabs, settings, db))


def run_tabs(settings: Settings, db: Database, ctx: JobContext) -> None:
    song_id = ctx.song_id
    if song_id is None:
        raise JobError("invalid_job", "Job delle tab senza brano.")
    storage = Storage(settings.data_dir)
    with db.read_session() as s:
        stems = {
            st.type: st
            for st in s.scalars(
                select(Stem).where(Stem.song_id == song_id, Stem.status == StemStatus.READY)
            )
        }
    wanted = [i for i, (stem_type, _t) in INSTRUMENTS.items() if stem_type in stems]
    if not wanted:
        raise JobError(
            "stems_missing",
            "Per le tab servono gli stem di chitarra o basso: separa prima il brano.",
        )

    ctx.stage(JobStatus.ANALYZING, "model", "Modello per le tab")
    ctx.run_phase("model", lambda: str(ensure_model(settings.data_dir)))
    model = BasicPitch(ensure_model(settings.data_dir))

    for n, instrument in enumerate(wanted):
        stem_type, tuning = INSTRUMENTS[instrument]
        label = "chitarra" if instrument is Instrument.GUITAR else "basso"
        ctx.stage(
            JobStatus.ANALYZING,
            instrument.value,
            f"Note della {label}" if instrument is Instrument.GUITAR else "Note del basso",
        )
        ctx.progress(0.05 + 0.9 * n / len(wanted))
        path = storage.to_absolute(stems[stem_type].path or "")

        def compute(path: Any = path, tuning: tuple[int, ...] = tuning) -> list[dict[str, Any]]:
            audio = load_audio(path)
            output = model.infer(audio, ctx.check)
            low, high = playable_range(tuning)
            notes = notes_from_output(output, min_midi=low, max_midi=high, check=ctx.check)
            return [asdict(f) for f in assign(notes, tuning)]

        ctx.run_phase(instrument.value, compute)

    ctx.stage(JobStatus.ANALYZING, "save", "Salvataggio delle tab")
    ctx.run_phase("save", lambda: _save(db, song_id, ctx, wanted))
    ctx.progress(1.0, eta_s=0)


def _save(
    db: Database, song_id: str, ctx: JobContext, instruments: list[Instrument]
) -> dict[str, int]:
    counts: dict[str, int] = {}
    with db.session() as s:
        if s.get(Song, song_id) is None:
            raise JobError("song_not_found", "Il brano è stato eliminato.")
        for instrument in instruments:
            notes = [FrettedNote(**n) for n in ctx.phase_result(instrument.value)]
            s.execute(
                delete(TabNote).where(TabNote.song_id == song_id, TabNote.instrument == instrument)
            )
            s.add_all(
                TabNote(
                    song_id=song_id,
                    instrument=instrument,
                    string=n.string,
                    fret=n.fret,
                    pitch_midi=n.pitch_midi,
                    start_s=n.start_s,
                    duration_s=n.duration_s,
                    velocity=n.velocity,
                    confidence=n.velocity,
                )
                for n in notes
            )
            counts[instrument.value] = len(notes)
    log.info("tab salvate", extra={"song_id": song_id, **counts})
    return counts
