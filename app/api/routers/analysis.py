"""Risultati dell'analisi: beat grid, accordi, sezioni, tonalità, BPM e waveform."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.analysis.jobs import waveform_path
from app.api.deps import DatabaseDep, SongsDep, StorageDep
from app.api.schemas import ImportStartedOut, JobOut, SongOut
from app.db.models import Beat, ChordEvent, Origin, Section
from app.errors import AppError

router = APIRouter(prefix="/songs", tags=["analysis"])


class BeatOut(BaseModel):
    time_s: float
    is_downbeat: bool
    bar: int | None


class ChordOut(BaseModel):
    id: str
    start_s: float
    end_s: float
    chord: str
    original_chord: str | None
    confidence: float | None
    beat_position: int | None
    origin: Origin


class SectionOut(BaseModel):
    id: str
    name: str
    color: str
    start_s: float
    end_s: float
    origin: Origin


class AnalysisOut(BaseModel):
    song_id: str
    analyzed: bool
    bpm: float | None
    bpm_confidence: float | None
    beats_per_bar: int
    beat_offset_s: float
    key: str | None
    key_confidence: float | None
    beats: list[BeatOut]
    chords: list[ChordOut]
    sections: list[SectionOut]


def _chords(db: DatabaseDep, song_id: str) -> list[ChordOut]:
    with db.read_session() as s:
        rows = s.scalars(
            select(ChordEvent)
            .where(ChordEvent.song_id == song_id, ChordEvent.is_deleted.is_(False))
            .order_by(ChordEvent.start_s)
        )
        return [
            ChordOut(
                id=c.id,
                start_s=c.start_s,
                end_s=c.end_s,
                chord=c.chord,
                original_chord=c.original_chord,
                confidence=c.confidence,
                beat_position=c.beat_position,
                origin=c.origin,
            )
            for c in rows
        ]


@router.get("/{song_id}/analysis", response_model=AnalysisOut)
def get_analysis(song_id: str, songs: SongsDep, db: DatabaseDep) -> AnalysisOut:
    song = songs.get(song_id)
    offset = song.beat_offset_s
    with db.read_session() as s:
        beats = [
            BeatOut(time_s=round(b.time_s + offset, 4), is_downbeat=b.is_downbeat, bar=b.bar)
            for b in s.scalars(select(Beat).where(Beat.song_id == song_id).order_by(Beat.position))
        ]
        sections = [
            SectionOut(
                id=x.id,
                name=x.name,
                color=x.color,
                start_s=x.start_s,
                end_s=x.end_s,
                origin=x.origin,
            )
            for x in s.scalars(
                select(Section)
                .where(Section.song_id == song_id, Section.is_deleted.is_(False))
                .order_by(Section.start_s)
            )
        ]
    chords = _chords(db, song_id)
    return AnalysisOut(
        song_id=song_id,
        analyzed=bool(beats or chords or sections),
        bpm=song.bpm,
        bpm_confidence=song.bpm_confidence,
        beats_per_bar=song.beats_per_bar,
        beat_offset_s=offset,
        key=song.key,
        key_confidence=song.key_confidence,
        beats=beats,
        chords=chords,
        sections=sections,
    )


@router.get("/{song_id}/chords", response_model=list[ChordOut])
def get_chords(song_id: str, songs: SongsDep, db: DatabaseDep) -> list[ChordOut]:
    songs.get(song_id)
    return _chords(db, song_id)


@router.get("/{song_id}/waveform", response_class=FileResponse)
def get_waveform(song_id: str, songs: SongsDep, storage: StorageDep) -> FileResponse:
    songs.get(song_id)
    path = waveform_path(storage, song_id)
    if not path.is_file():
        raise AppError("waveform_not_found", "La waveform non è ancora stata calcolata.")
    return FileResponse(path, media_type="application/json")


@router.post("/{song_id}/analyze", response_model=ImportStartedOut)
def reanalyze(song_id: str, request: Request, songs: SongsDep) -> ImportStartedOut:
    job_id = songs.analyze(song_id)
    job = request.app.state.queue.get(job_id)
    song = songs.get(song_id)
    return ImportStartedOut(
        song=SongOut.from_song(song, job, has_audio=True), job=JobOut.from_job(job)
    )
