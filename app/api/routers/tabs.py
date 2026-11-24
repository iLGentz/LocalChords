"""Tab indicative di chitarra e basso."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DatabaseDep, QueueDep, SongsDep
from app.api.schemas import JobOut
from app.db.models import Instrument, Job, Stem, StemStatus, StemType, TabNote
from app.errors import AppError
from app.importing.service import ACTIVE_JOB_STATUSES
from app.tabs.fretting import BASS_TUNING, GUITAR_TUNING
from app.tabs.jobs import TABS

router = APIRouter(prefix="/songs", tags=["tabs"])


class TabNoteOut(BaseModel):
    string: int
    fret: int
    pitch_midi: int
    start_s: float
    duration_s: float


class InstrumentTabOut(BaseModel):
    tuning: list[int]
    """MIDI delle corde a vuoto, dalla più grave alla più acuta."""
    notes: list[TabNoteOut]


class TabsOut(BaseModel):
    available_stems: list[str]
    guitar: InstrumentTabOut | None
    bass: InstrumentTabOut | None
    job: JobOut | None


@router.get("/{song_id}/tabs", response_model=TabsOut)
def get_tabs(song_id: str, songs: SongsDep, db: DatabaseDep) -> TabsOut:
    songs.get(song_id)
    with db.read_session() as s:
        notes = list(
            s.scalars(select(TabNote).where(TabNote.song_id == song_id).order_by(TabNote.start_s))
        )
        stems = [
            st.type.value
            for st in s.scalars(
                select(Stem).where(Stem.song_id == song_id, Stem.status == StemStatus.READY)
            )
            if st.type in (StemType.GUITAR, StemType.BASS)
        ]
        job = s.scalars(
            select(Job)
            .where(Job.song_id == song_id, Job.kind == TABS)
            .order_by(Job.created_at.desc())
            .limit(1)
        ).first()

    def pack(instrument: Instrument, tuning: tuple[int, ...]) -> InstrumentTabOut | None:
        chosen = [n for n in notes if n.instrument is instrument]
        if not chosen:
            return None
        return InstrumentTabOut(
            tuning=list(tuning),
            notes=[
                TabNoteOut(
                    string=n.string,
                    fret=n.fret,
                    pitch_midi=n.pitch_midi,
                    start_s=n.start_s,
                    duration_s=n.duration_s,
                )
                for n in chosen
            ],
        )

    return TabsOut(
        available_stems=stems,
        guitar=pack(Instrument.GUITAR, GUITAR_TUNING),
        bass=pack(Instrument.BASS, BASS_TUNING),
        job=JobOut.from_job(job) if job else None,
    )


@router.post("/{song_id}/tabs", response_model=JobOut, status_code=202)
def generate_tabs(song_id: str, songs: SongsDep, db: DatabaseDep, queue: QueueDep) -> JobOut:
    songs.get(song_id)
    with db.read_session() as s:
        has_stems = s.scalars(
            select(Stem).where(
                Stem.song_id == song_id,
                Stem.status == StemStatus.READY,
                Stem.type.in_((StemType.GUITAR, StemType.BASS)),
            )
        ).first()
        busy = s.scalars(
            select(Job).where(Job.song_id == song_id, Job.status.in_(ACTIVE_JOB_STATUSES))
        ).first()
    if has_stems is None:
        raise AppError("stems_missing", "Per le tab servono gli stem: separa prima il brano.")
    if busy is not None:
        raise AppError("song_busy", "Il brano è in elaborazione: riprova al termine.")
    job = queue.get(queue.enqueue(TABS, {}, song_id=song_id))
    assert job is not None
    return JobOut.from_job(job)
