"""Trasposizione, capo, semplificazione, preferenze di visualizzazione e modifica degli accordi."""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.api.deps import DatabaseDep, SongsDep
from app.api.schemas import SongOut
from app.db.models import ChordEvent, Simplification, Song
from app.editing.history import EditGroup
from app.errors import AppError
from app.preferences import DisplayPreferences, load_display, save_display

router = APIRouter(tags=["practice"])

# Simbolo accordo: fondamentale, suffisso libero breve, basso opzionale; "N" = nessun accordo.
_CHORD = re.compile(r"^(N|[A-G](#|b)?[A-Za-z0-9+#()b-]{0,12}(/[A-G](#|b)?)?)$")


class ViewIn(BaseModel):
    transpose: Annotated[int | None, Field(default=None, ge=-11, le=11)] = None
    capo: Annotated[int | None, Field(default=None, ge=0, le=11)] = None
    simplification: Simplification | None = None


@router.patch("/songs/{song_id}/view", response_model=SongOut)
def update_view(song_id: str, body: ViewIn, songs: SongsDep, db: DatabaseDep) -> SongOut:
    songs.get(song_id)
    with db.session() as s:
        song = s.get_one(Song, song_id)
        for key in body.model_fields_set:
            value = getattr(body, key)
            if value is not None:
                setattr(song, key, value)
    return SongOut.from_song(
        songs.get(song_id), songs.latest_jobs([song_id]).get(song_id), has_audio=True
    )


@router.get("/settings/display", response_model=DisplayPreferences)
def get_display(db: DatabaseDep) -> DisplayPreferences:
    return load_display(db)


@router.put("/settings/display", response_model=DisplayPreferences)
def put_display(body: DisplayPreferences, db: DatabaseDep) -> DisplayPreferences:
    return save_display(db, body)


class ChordUpdateIn(BaseModel):
    chord: Annotated[str | None, Field(default=None, max_length=32)] = None
    simplify_exempt: bool | None = None


def _chord(s: Any, song_id: str, chord_id: str) -> ChordEvent:
    chord: ChordEvent | None = s.get(ChordEvent, chord_id)
    if chord is None or chord.song_id != song_id:
        raise AppError("chord_not_found", "Accordo non trovato.")
    return chord


@router.patch("/songs/{song_id}/chords/{chord_id}", status_code=204)
def update_chord(
    song_id: str, chord_id: str, body: ChordUpdateIn, songs: SongsDep, db: DatabaseDep
) -> Response:
    songs.get(song_id)
    changes: dict[str, Any] = {}
    if body.chord is not None:
        symbol = body.chord.strip()
        if not _CHORD.match(symbol):
            raise AppError("invalid_chord", f"Simbolo di accordo non valido: «{symbol}».")
        changes["chord"] = symbol
    if body.simplify_exempt is not None:
        changes["simplify_exempt"] = body.simplify_exempt
    with db.session() as s:
        EditGroup(s, song_id).update("chord", _chord(s, song_id, chord_id), changes)
    return Response(status_code=204)


@router.post("/songs/{song_id}/chords/{chord_id}/restore", status_code=204)
def restore_chord(song_id: str, chord_id: str, songs: SongsDep, db: DatabaseDep) -> Response:
    songs.get(song_id)
    with db.session() as s:
        chord = _chord(s, song_id, chord_id)
        EditGroup(s, song_id).update(
            "chord",
            chord,
            {
                "chord": chord.original_chord or chord.chord,
                "start_s": chord.original_start_s
                if chord.original_start_s is not None
                else chord.start_s,
                "end_s": chord.original_end_s if chord.original_end_s is not None else chord.end_s,
                "simplify_exempt": False,
            },
        )
    return Response(status_code=204)
