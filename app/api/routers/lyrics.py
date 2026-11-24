"""Testi sincronizzati: lettura, editor (righe e parole), nuova ricerca, annulla/ripristina."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DatabaseDep, QueueDep, SettingsDep, SongsDep
from app.api.schemas import JobOut
from app.db.models import Job, LyricLine, LyricWord, Origin
from app.editing import history
from app.errors import AppError
from app.importing.service import ACTIVE_JOB_STATUSES
from app.lyrics import editor
from app.lyrics.jobs import LYRICS, plan_whisper

router = APIRouter(prefix="/songs", tags=["lyrics"])

Seconds = Annotated[float | None, Field(default=None, ge=0, le=6 * 3600)]


class WordOut(BaseModel):
    id: str
    text: str
    start_s: float | None
    end_s: float | None
    confidence: float | None
    edited: bool
    origin: Origin


class LineOut(BaseModel):
    id: str
    text: str
    start_s: float | None
    end_s: float | None
    original_text: str | None
    edited: bool
    origin: Origin
    words: list[WordOut]


class WhisperInfo(BaseModel):
    model_id: str
    label: str
    size_mb: int
    installed: bool
    device: str


class LyricsOut(BaseModel):
    source: str | None
    status: str | None
    """aligned, line_synced, unsynced, transcribed, instrumental, no_voice, model_missing."""
    note: str | None
    language: str | None
    lrclib_enabled: bool
    whisper: WhisperInfo
    can_undo: bool
    can_redo: bool
    job: JobOut | None
    lines: list[LineOut]


def _edited_line(ln: LyricLine) -> bool:
    return ln.origin is Origin.USER or (ln.text, ln.start_s, ln.end_s) != (
        ln.original_text,
        ln.original_start_s,
        ln.original_end_s,
    )


def _edited_word(w: LyricWord) -> bool:
    return w.origin is Origin.USER or (w.text, w.start_s, w.end_s) != (
        w.original_text,
        w.original_start_s,
        w.original_end_s,
    )


@router.get("/{song_id}/lyrics", response_model=LyricsOut)
def get_lyrics(song_id: str, songs: SongsDep, db: DatabaseDep, settings: SettingsDep) -> LyricsOut:
    song = songs.get(song_id)
    with db.read_session() as s:
        lines = list(
            s.scalars(
                select(LyricLine)
                .where(LyricLine.song_id == song_id, LyricLine.is_deleted.is_(False))
                .order_by(LyricLine.position)
            )
        )
        words: dict[str, list[LyricWord]] = {}
        if lines:
            for w in s.scalars(
                select(LyricWord)
                .where(
                    LyricWord.line_id.in_([ln.id for ln in lines]),
                    LyricWord.is_deleted.is_(False),
                )
                .order_by(LyricWord.position)
            ):
                words.setdefault(w.line_id, []).append(w)
        job = s.scalars(
            select(Job)
            .where(Job.song_id == song_id, Job.kind == LYRICS)
            .order_by(Job.created_at.desc())
            .limit(1)
        ).first()
    data: dict[str, Any] = (job.checkpoint or {}).get("data", {}) if job else {}
    align = data.get("align") or {}
    reference = data.get("reference") or {}
    plan = plan_whisper(settings, db, song.duration_s)
    hstate = history.state(db, song_id)
    return LyricsOut(
        source=song.lyrics_source.value if song.lyrics_source else None,
        status=align.get("status"),
        note=reference.get("note"),
        language=align.get("language"),
        lrclib_enabled=settings.lrclib_enabled,
        whisper=WhisperInfo(
            model_id=plan.model.id,
            label=plan.model.label,
            size_mb=plan.model.size_mb,
            installed=plan.installed,
            device=plan.device.value,
        ),
        can_undo=hstate.can_undo,
        can_redo=hstate.can_redo,
        job=JobOut.from_job(job) if job else None,
        lines=[
            LineOut(
                id=ln.id,
                text=ln.text,
                start_s=ln.start_s,
                end_s=ln.end_s,
                original_text=ln.original_text,
                edited=_edited_line(ln),
                origin=ln.origin,
                words=[
                    WordOut(
                        id=w.id,
                        text=w.text,
                        start_s=w.start_s,
                        end_s=w.end_s,
                        confidence=w.confidence,
                        edited=_edited_word(w),
                        origin=w.origin,
                    )
                    for w in words.get(ln.id, [])
                ],
            )
            for ln in lines
        ],
    )


# ------------------------------------------------------------------ editor


class LineUpdateIn(BaseModel):
    text: Annotated[str | None, Field(default=None, max_length=2000)] = None
    start_s: Seconds = None
    end_s: Seconds = None


class LineCreateIn(BaseModel):
    after_line_id: str | None = None
    text: Annotated[str, Field(min_length=1, max_length=2000)]
    start_s: Seconds = None
    end_s: Seconds = None


class WordUpdateIn(BaseModel):
    text: Annotated[str | None, Field(default=None, max_length=200)] = None
    start_s: Seconds = None
    end_s: Seconds = None


class WordCreateIn(BaseModel):
    after_word_id: str | None = None
    text: Annotated[str, Field(min_length=1, max_length=200)]


class CreatedOut(BaseModel):
    id: str


def _changes(body: BaseModel) -> dict[str, Any]:
    """Solo i campi inviati: ``null`` esplicito azzera un tempo, un campo assente no."""
    return {k: getattr(body, k) for k in body.model_fields_set}


@router.patch("/{song_id}/lyrics/{line_id}", status_code=204)
def patch_line(song_id: str, line_id: str, body: LineUpdateIn, db: DatabaseDep) -> Response:
    editor.update_line(db, song_id, line_id, _changes(body))
    return Response(status_code=204)


@router.post("/{song_id}/lyrics/lines", response_model=CreatedOut, status_code=201)
def create_line(song_id: str, body: LineCreateIn, db: DatabaseDep) -> CreatedOut:
    return CreatedOut(
        id=editor.insert_line(db, song_id, body.after_line_id, body.text, body.start_s, body.end_s)
    )


@router.delete("/{song_id}/lyrics/{line_id}", status_code=204)
def remove_line(song_id: str, line_id: str, db: DatabaseDep) -> Response:
    editor.delete_line(db, song_id, line_id)
    return Response(status_code=204)


@router.post("/{song_id}/lyrics/restore", status_code=204)
def restore_all(song_id: str, db: DatabaseDep) -> Response:
    editor.restore_all(db, song_id)
    return Response(status_code=204)


@router.post("/{song_id}/lyrics/{line_id}/restore", status_code=204)
def restore_line(song_id: str, line_id: str, db: DatabaseDep) -> Response:
    editor.restore_line(db, song_id, line_id)
    return Response(status_code=204)


@router.patch("/{song_id}/lyrics/words/{word_id}", status_code=204)
def patch_word(song_id: str, word_id: str, body: WordUpdateIn, db: DatabaseDep) -> Response:
    editor.update_word(db, song_id, word_id, _changes(body))
    return Response(status_code=204)


@router.post("/{song_id}/lyrics/{line_id}/words", response_model=CreatedOut, status_code=201)
def create_word(song_id: str, line_id: str, body: WordCreateIn, db: DatabaseDep) -> CreatedOut:
    return CreatedOut(id=editor.insert_word(db, song_id, line_id, body.after_word_id, body.text))


@router.delete("/{song_id}/lyrics/words/{word_id}", status_code=204)
def remove_word(song_id: str, word_id: str, db: DatabaseDep) -> Response:
    editor.delete_word(db, song_id, word_id)
    return Response(status_code=204)


# ------------------------------------------------------------- nuova ricerca


class RefreshIn(BaseModel):
    text: Annotated[str | None, Field(default=None, max_length=50_000)] = None
    """Testo incollato (anche in formato LRC). Se assente si cerca su LRCLIB."""
    search: bool = True


@router.post("/{song_id}/lyrics/refresh", response_model=JobOut, status_code=202)
def refresh_lyrics(
    song_id: str, body: RefreshIn, songs: SongsDep, db: DatabaseDep, queue: QueueDep
) -> JobOut:
    songs.get(song_id)
    with db.read_session() as s:
        busy = s.scalars(
            select(Job).where(Job.song_id == song_id, Job.status.in_(ACTIVE_JOB_STATUSES))
        ).first()
    if busy is not None:
        raise AppError("song_busy", "Il brano è in elaborazione: riprova al termine.")
    payload: dict[str, Any] = {"search": body.search}
    if body.text and body.text.strip():
        payload["text"] = body.text
    job = queue.get(queue.enqueue(LYRICS, payload, song_id=song_id))
    assert job is not None
    return JobOut.from_job(job)


# ---------------------------------------------------------- annulla/ripristina


class HistoryOut(BaseModel):
    entity_types: list[str]
    can_undo: bool
    can_redo: bool


@router.post("/{song_id}/undo", response_model=HistoryOut)
def undo(song_id: str, songs: SongsDep, db: DatabaseDep) -> HistoryOut:
    songs.get(song_id)
    types = history.undo(db, song_id)
    st = history.state(db, song_id)
    return HistoryOut(entity_types=types, can_undo=st.can_undo, can_redo=st.can_redo)


@router.post("/{song_id}/redo", response_model=HistoryOut)
def redo(song_id: str, songs: SongsDep, db: DatabaseDep) -> HistoryOut:
    songs.get(song_id)
    types = history.redo(db, song_id)
    st = history.state(db, song_id)
    return HistoryOut(entity_types=types, can_undo=st.can_undo, can_redo=st.can_redo)
