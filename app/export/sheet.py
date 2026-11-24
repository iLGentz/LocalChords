"""Spartito "accordi sopra il testo" in forma strutturata, base per TXT, ChordPro e PDF.

I nomi degli accordi arrivano già trasformati dal frontend (``labels``: semplificazione,
trasposizione, capo e notazione), così la teoria musicale ha una sola implementazione
(``frontend/src/lib/music.ts``). Qui si ricostruiscono:
- per ogni riga del testo, la posizione di ogni accordo sopra la parola in cui cade;
- per le parti strumentali (accordi senza testo sotto), righe di soli accordi;
- i titoli di sezione.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select

from app.db.models import ChordEvent, LyricLine, LyricWord, Section, Song
from app.db.session import Database

CHORD_LEAD_S = 0.3
INSTRUMENTAL_PER_LINE = 8


@dataclass
class LyricBlock:
    text: str
    chords: list[tuple[int, str]]
    """(colonna nel testo, nome accordo)."""


@dataclass
class ChordsBlock:
    labels: list[str]


@dataclass
class SectionBlock:
    name: str


Block = LyricBlock | ChordsBlock | SectionBlock


@dataclass
class SheetMeta:
    title: str
    artist: str | None
    album: str | None
    key: str | None
    capo: int
    bpm: float | None
    notes: list[str] = field(default_factory=list)


@dataclass
class Sheet:
    meta: SheetMeta
    blocks: list[Block]


def build_sheet(db: Database, song_id: str, labels: dict[str, str], meta: SheetMeta) -> Sheet:
    with db.read_session() as s:
        chords = [
            c
            for c in s.scalars(
                select(ChordEvent)
                .where(ChordEvent.song_id == song_id, ChordEvent.is_deleted.is_(False))
                .order_by(ChordEvent.start_s)
            )
            if c.chord != "N"
        ]
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
                    LyricWord.line_id.in_([ln.id for ln in lines]), LyricWord.is_deleted.is_(False)
                )
                .order_by(LyricWord.position)
            ):
                words.setdefault(w.line_id, []).append(w)
        sections = list(
            s.scalars(
                select(Section)
                .where(Section.song_id == song_id, Section.is_deleted.is_(False))
                .order_by(Section.start_s)
            )
        )
        if s.get(Song, song_id) is None:
            return Sheet(meta, [])

    def label(c: ChordEvent) -> str:
        return labels.get(c.id, c.chord)

    # Eventi in ordine di tempo: sezioni, righe temporizzate, accordi.
    timed_lines = [ln for ln in lines if ln.start_s is not None]
    untimed_lines = [ln for ln in lines if ln.start_s is None]
    used: set[str] = set()
    events: list[tuple[float, int, Block]] = []

    for sec in sections:
        events.append((sec.start_s, 0, SectionBlock(sec.name)))

    for i, ln in enumerate(timed_lines):
        start = ln.start_s or 0.0
        nxt = timed_lines[i + 1].start_s if i + 1 < len(timed_lines) else None
        end = ln.end_s if ln.end_s is not None else (nxt if nxt is not None else start + 4.0)
        line_words = words.get(ln.id, [])
        text, columns = _layout(ln.text, line_words)
        placed: list[tuple[int, str]] = []
        for c in chords:
            if c.id in used or c.start_s < start - CHORD_LEAD_S or c.start_s >= end:
                continue
            col = 0
            for w, column in zip(line_words, columns, strict=True):
                if w.start_s is not None and w.start_s <= c.start_s + 0.15:
                    col = column
            placed.append((col, label(c)))
            used.add(c.id)
        events.append((start, 1, LyricBlock(text, placed)))

    # Accordi rimasti (introduzioni, assoli, finali): righe di soli accordi.
    pending: list[ChordEvent] = []

    def flush() -> None:
        for k in range(0, len(pending), INSTRUMENTAL_PER_LINE):
            chunk = pending[k : k + INSTRUMENTAL_PER_LINE]
            events.append((chunk[0].start_s, 2, ChordsBlock([label(c) for c in chunk])))
        pending.clear()

    line_starts = sorted(ln.start_s or 0.0 for ln in timed_lines)
    for c in chords:
        if c.id in used:
            continue
        if pending and any(pending[-1].start_s < t <= c.start_s for t in line_starts):
            flush()
        pending.append(c)
    flush()

    events.sort(key=lambda e: (e[0], e[1]))
    blocks: list[Block] = [b for _t, _o, b in events]
    blocks.extend(LyricBlock(ln.text, []) for ln in untimed_lines)
    return Sheet(meta, blocks)


def _layout(text: str, line_words: list[LyricWord]) -> tuple[str, list[int]]:
    """Testo della riga e colonna iniziale di ogni parola."""
    if not line_words:
        return text, []
    columns: list[int] = []
    out = ""
    for w in line_words:
        if out:
            out += " "
        columns.append(len(out))
        out += w.text
    return out, columns


def chord_line(block: LyricBlock) -> str:
    """Riga degli accordi allineata al testo (senza sovrapposizioni)."""
    line = ""
    for col, name in sorted(block.chords):
        start = max(col, len(line) + 1 if line else col)
        line = line.ljust(start) + name
    return line
