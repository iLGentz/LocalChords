"""Cronologia persistente delle modifiche (annulla / ripristina), tabella ``edit_history``.

Ogni modifica è un aggiornamento di campi: creare un elemento vuol dire passare
``is_deleted`` da vero a falso, eliminarlo il contrario. Così annullare = riapplicare
``before``, ripristinare = riapplicare ``after``, per qualsiasi tipo di entità.

Le voci con lo stesso ``group_id`` formano un passo unico. Una nuova modifica scarta lo stack
di "ripristina" del brano.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.base import new_id, utcnow
from app.db.models import ChordEvent, EditAction, EditHistory, LyricLine, LyricWord, Section
from app.db.session import Database
from app.errors import AppError

ENTITY_MODELS: dict[str, Any] = {
    "lyric_line": LyricLine,
    "lyric_word": LyricWord,
    "chord": ChordEvent,
    "section": Section,
}


@dataclass(frozen=True)
class HistoryState:
    can_undo: bool
    can_redo: bool


class EditGroup:
    """Raccoglie le modifiche di un'operazione utente dentro una sessione."""

    def __init__(self, session: Session, song_id: str) -> None:
        self.session = session
        self.song_id = song_id
        self.group_id = new_id()
        self._cleared = False

    def _clear_redo(self) -> None:
        if not self._cleared:
            self.session.execute(
                delete(EditHistory).where(
                    EditHistory.song_id == self.song_id, EditHistory.undone.is_(True)
                )
            )
            self._cleared = True

    def update(self, entity_type: str, entity: Any, changes: dict[str, Any]) -> None:
        """Applica ``changes`` all'entità registrando i valori precedenti."""
        before = {k: getattr(entity, k) for k in changes}
        if before == changes:
            return
        self._clear_redo()
        for key, value in changes.items():
            setattr(entity, key, value)
        entity.updated_at = utcnow()
        self._add(entity_type, entity.id, EditAction.UPDATE, before, dict(changes))

    def created(self, entity_type: str, entity: Any) -> None:
        self._clear_redo()
        self._add(
            entity_type, entity.id, EditAction.CREATE, {"is_deleted": True}, {"is_deleted": False}
        )

    def deleted(self, entity_type: str, entity: Any) -> None:
        if entity.is_deleted:
            return
        self._clear_redo()
        entity.is_deleted = True
        entity.updated_at = utcnow()
        self._add(
            entity_type, entity.id, EditAction.DELETE, {"is_deleted": False}, {"is_deleted": True}
        )

    def _add(
        self,
        entity_type: str,
        entity_id: str,
        action: EditAction,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        self.session.add(
            EditHistory(
                song_id=self.song_id,
                group_id=self.group_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                before=before,
                after=after,
            )
        )


def _apply(session: Session, entries: list[EditHistory], use_before: bool) -> None:
    for entry in entries:
        model = ENTITY_MODELS.get(entry.entity_type)
        if model is None:
            continue
        entity = session.get(model, entry.entity_id)
        if entity is None:
            continue
        values = entry.before if use_before else entry.after
        for key, value in (values or {}).items():
            setattr(entity, key, value)
        entity.updated_at = utcnow()


def undo(db: Database, song_id: str) -> list[str]:
    """Annulla l'ultimo passo. Restituisce i tipi di entità toccati."""
    with db.session() as s:
        last = s.scalar(
            select(func.max(EditHistory.id)).where(
                EditHistory.song_id == song_id, EditHistory.undone.is_(False)
            )
        )
        if last is None:
            raise AppError("nothing_to_undo", "Niente da annullare.")
        group = s.get_one(EditHistory, last).group_id
        entries = list(
            s.scalars(
                select(EditHistory)
                .where(EditHistory.song_id == song_id, EditHistory.group_id == group)
                .order_by(EditHistory.id.desc())
            )
        )
        _apply(s, entries, use_before=True)
        for e in entries:
            e.undone = True
        return sorted({e.entity_type for e in entries})


def redo(db: Database, song_id: str) -> list[str]:
    """Ripristina il passo annullato più di recente."""
    with db.session() as s:
        first = s.scalar(
            select(func.min(EditHistory.id)).where(
                EditHistory.song_id == song_id, EditHistory.undone.is_(True)
            )
        )
        if first is None:
            raise AppError("nothing_to_redo", "Niente da ripristinare.")
        group = s.get_one(EditHistory, first).group_id
        entries = list(
            s.scalars(
                select(EditHistory)
                .where(EditHistory.song_id == song_id, EditHistory.group_id == group)
                .order_by(EditHistory.id)
            )
        )
        _apply(s, entries, use_before=False)
        for e in entries:
            e.undone = False
        return sorted({e.entity_type for e in entries})


def state(db: Database, song_id: str) -> HistoryState:
    with db.read_session() as s:
        can_undo = s.scalar(
            select(EditHistory.id)
            .where(EditHistory.song_id == song_id, EditHistory.undone.is_(False))
            .limit(1)
        )
        can_redo = s.scalar(
            select(EditHistory.id)
            .where(EditHistory.song_id == song_id, EditHistory.undone.is_(True))
            .limit(1)
        )
    return HistoryState(can_undo is not None, can_redo is not None)


def has_edits(session: Session, song_id: str, entity_types: tuple[str, ...]) -> bool:
    return (
        session.scalar(
            select(EditHistory.id)
            .where(EditHistory.song_id == song_id, EditHistory.entity_type.in_(entity_types))
            .limit(1)
        )
        is not None
    )


def forget(session: Session, song_id: str, entity_types: tuple[str, ...]) -> None:
    """Rimuove la cronologia di entità che vengono rigenerate (es. nuova analisi)."""
    session.execute(
        delete(EditHistory).where(
            EditHistory.song_id == song_id, EditHistory.entity_type.in_(entity_types)
        )
    )
