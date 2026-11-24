"""Modifiche manuali a righe e parole del testo, con cronologia (annulla/ripristina).

Regole:
- cambiare il testo di una riga ricostruisce le parole: se il numero di parole non cambia si
  conservano i tempi, altrimenti si distribuiscono nell'intervallo della riga;
- le eliminazioni sono logiche (``is_deleted``), così "ripristina originale" e "annulla"
  funzionano sempre;
- le posizioni sono spaziate (1024) per inserire senza rinumerare.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LyricLine, LyricWord, Origin, Song
from app.db.session import Database
from app.editing.history import EditGroup
from app.errors import AppError
from app.lyrics.align import tokenize

STEP = 1024


def _line(s: Session, song_id: str, line_id: str) -> LyricLine:
    line = s.get(LyricLine, line_id)
    if line is None or line.song_id != song_id:
        raise AppError("lyric_line_not_found", "Riga del testo non trovata.")
    return line


def _word(s: Session, song_id: str, word_id: str) -> tuple[LyricWord, LyricLine]:
    word = s.get(LyricWord, word_id)
    if word is None:
        raise AppError("lyric_word_not_found", "Parola non trovata.")
    line = _line(s, song_id, word.line_id)
    return word, line


def _live_words(s: Session, line_id: str) -> list[LyricWord]:
    return list(
        s.scalars(
            select(LyricWord)
            .where(LyricWord.line_id == line_id, LyricWord.is_deleted.is_(False))
            .order_by(LyricWord.position)
        )
    )


def _check_times(start: float | None, end: float | None) -> None:
    if start is not None and start < 0:
        raise AppError("invalid_time", "Il tempo non può essere negativo.")
    if start is not None and end is not None and end < start:
        raise AppError("invalid_time", "La fine deve venire dopo l'inizio.")


def _distribute(
    start: float | None, end: float | None, tokens: list[str]
) -> list[tuple[float | None, float | None]]:
    if start is None or end is None or end <= start or not tokens:
        return [(None, None)] * len(tokens)
    weights = [max(len(t), 1) for t in tokens]
    total = float(sum(weights))
    out: list[tuple[float | None, float | None]] = []
    t = start
    for w in weights:
        span = (end - start) * w / total
        out.append((round(t, 3), round(t + span * 0.9, 3)))
        t += span
    return out


def _retokenize(s: Session, g: EditGroup, line: LyricLine, text: str) -> None:
    tokens = tokenize(text)
    words = _live_words(s, line.id)
    if len(tokens) == len(words):
        for w, tok in zip(words, tokens, strict=True):
            g.update("lyric_word", w, {"text": tok})
        return
    for w in words:
        g.deleted("lyric_word", w)
    for i, ((start, end), tok) in enumerate(
        zip(_distribute(line.start_s, line.end_s, tokens), tokens, strict=True)
    ):
        word = LyricWord(
            line_id=line.id,
            position=(i + 1) * STEP + (words[-1].position if words else 0),
            text=tok,
            start_s=start,
            end_s=end,
            origin=Origin.USER,
        )
        s.add(word)
        s.flush()
        g.created("lyric_word", word)


def update_line(db: Database, song_id: str, line_id: str, changes: dict[str, Any]) -> None:
    with db.session() as s:
        line = _line(s, song_id, line_id)
        g = EditGroup(s, song_id)
        start = changes.get("start_s", line.start_s)
        end = changes.get("end_s", line.end_s)
        _check_times(start, end)
        fields = {k: v for k, v in changes.items() if k in ("start_s", "end_s")}
        if "text" in changes:
            text = " ".join(str(changes["text"]).split())
            if not text:
                raise AppError("empty_text", "La riga non può essere vuota: eliminala.")
            fields["text"] = text
        if "start_s" in fields and line.start_s is not None and fields["start_s"] is not None:
            # Spostare l'inizio della riga sposta anche le sue parole.
            delta = float(fields["start_s"]) - line.start_s
            for w in _live_words(s, line.id):
                if w.start_s is not None and w.end_s is not None:
                    g.update(
                        "lyric_word",
                        w,
                        {
                            "start_s": round(w.start_s + delta, 3),
                            "end_s": round(w.end_s + delta, 3),
                        },
                    )
            if "end_s" not in fields and line.end_s is not None:
                fields["end_s"] = round(line.end_s + delta, 3)
        g.update("lyric_line", line, fields)
        if "text" in fields:
            _retokenize(s, g, line, fields["text"])


def insert_line(
    db: Database,
    song_id: str,
    after_line_id: str | None,
    text: str,
    start_s: float | None,
    end_s: float | None,
) -> str:
    text = " ".join(text.split())
    if not text:
        raise AppError("empty_text", "Scrivi il testo della riga.")
    _check_times(start_s, end_s)
    with db.session() as s:
        if s.get(Song, song_id) is None:
            raise AppError("song_not_found", "Brano non trovato.")
        lines = list(
            s.scalars(
                select(LyricLine).where(LyricLine.song_id == song_id).order_by(LyricLine.position)
            )
        )
        if after_line_id is None:
            prev_pos, next_pos = 0, (lines[0].position if lines else 2 * STEP)
        else:
            idx = next((i for i, ln in enumerate(lines) if ln.id == after_line_id), None)
            if idx is None:
                raise AppError("lyric_line_not_found", "Riga del testo non trovata.")
            prev_pos = lines[idx].position
            next_pos = lines[idx + 1].position if idx + 1 < len(lines) else prev_pos + 2 * STEP
        if next_pos - prev_pos < 2:
            for i, ln in enumerate(lines):  # rinumerazione: l'ordine non fa parte della cronologia
                ln.position = (i + 1) * STEP
            return _insert_after_renumber(s, song_id, lines, after_line_id, text, start_s, end_s)
        line = LyricLine(
            song_id=song_id,
            position=(prev_pos + next_pos) // 2,
            text=text,
            start_s=start_s,
            end_s=end_s,
            origin=Origin.USER,
        )
        return _finish_insert(s, song_id, line)


def _insert_after_renumber(
    s: Session,
    song_id: str,
    lines: list[LyricLine],
    after_line_id: str | None,
    text: str,
    start_s: float | None,
    end_s: float | None,
) -> str:
    if after_line_id is None:
        position = STEP // 2
    else:
        idx = next(i for i, ln in enumerate(lines) if ln.id == after_line_id)
        position = lines[idx].position + STEP // 2
    line = LyricLine(
        song_id=song_id,
        position=position,
        text=text,
        start_s=start_s,
        end_s=end_s,
        origin=Origin.USER,
    )
    return _finish_insert(s, song_id, line)


def _finish_insert(s: Session, song_id: str, line: LyricLine) -> str:
    s.add(line)
    s.flush()
    g = EditGroup(s, song_id)
    g.created("lyric_line", line)
    for i, ((ws, we), tok) in enumerate(
        zip(
            _distribute(line.start_s, line.end_s, tokenize(line.text)),
            tokenize(line.text),
            strict=True,
        )
    ):
        word = LyricWord(
            line_id=line.id,
            position=(i + 1) * STEP,
            text=tok,
            start_s=ws,
            end_s=we,
            origin=Origin.USER,
        )
        s.add(word)
        s.flush()
        g.created("lyric_word", word)
    return line.id


def delete_line(db: Database, song_id: str, line_id: str) -> None:
    with db.session() as s:
        line = _line(s, song_id, line_id)
        EditGroup(s, song_id).deleted("lyric_line", line)


def update_word(db: Database, song_id: str, word_id: str, changes: dict[str, Any]) -> None:
    with db.session() as s:
        word, line = _word(s, song_id, word_id)
        _check_times(changes.get("start_s", word.start_s), changes.get("end_s", word.end_s))
        fields = {k: v for k, v in changes.items() if k in ("start_s", "end_s")}
        if "text" in changes:
            text = str(changes["text"]).strip()
            if not text or len(tokenize(text)) != 1:
                raise AppError(
                    "invalid_word", "Una parola deve essere un solo termine, senza spazi."
                )
            fields["text"] = text
        g = EditGroup(s, song_id)
        g.update("lyric_word", word, fields)
        if "text" in fields:
            g.update(
                "lyric_line", line, {"text": " ".join(w.text for w in _live_words(s, line.id))}
            )


def insert_word(
    db: Database, song_id: str, line_id: str, after_word_id: str | None, text: str
) -> str:
    text = text.strip()
    if not text or len(tokenize(text)) != 1:
        raise AppError("invalid_word", "Una parola deve essere un solo termine, senza spazi.")
    with db.session() as s:
        line = _line(s, song_id, line_id)
        words = _live_words(s, line.id)
        if after_word_id is None:
            prev_pos = 0
            nxt = words[0] if words else None
        else:
            idx = next((i for i, w in enumerate(words) if w.id == after_word_id), None)
            if idx is None:
                raise AppError("lyric_word_not_found", "Parola non trovata.")
            prev_pos = words[idx].position
            nxt = words[idx + 1] if idx + 1 < len(words) else None
        next_pos = nxt.position if nxt else prev_pos + 2 * STEP
        if next_pos - prev_pos < 2:
            for i, w in enumerate(words):
                w.position = (i + 1) * STEP
            return insert_word_after_flush(s, song_id, line, after_word_id, text)
        word = LyricWord(
            line_id=line.id, position=(prev_pos + next_pos) // 2, text=text, origin=Origin.USER
        )
        s.add(word)
        s.flush()
        g = EditGroup(s, song_id)
        g.created("lyric_word", word)
        g.update("lyric_line", line, {"text": " ".join(w.text for w in _live_words(s, line.id))})
        return word.id


def insert_word_after_flush(
    s: Session, song_id: str, line: LyricLine, after_word_id: str | None, text: str
) -> str:
    s.flush()
    words = _live_words(s, line.id)
    position = STEP // 2
    if after_word_id is not None:
        idx = next(i for i, w in enumerate(words) if w.id == after_word_id)
        position = words[idx].position + STEP // 2
    word = LyricWord(line_id=line.id, position=position, text=text, origin=Origin.USER)
    s.add(word)
    s.flush()
    g = EditGroup(s, song_id)
    g.created("lyric_word", word)
    g.update("lyric_line", line, {"text": " ".join(w.text for w in _live_words(s, line.id))})
    return word.id


def delete_word(db: Database, song_id: str, word_id: str) -> None:
    with db.session() as s:
        word, line = _word(s, song_id, word_id)
        g = EditGroup(s, song_id)
        g.deleted("lyric_word", word)
        s.flush()
        remaining = _live_words(s, line.id)
        if remaining:
            g.update("lyric_line", line, {"text": " ".join(w.text for w in remaining)})
        else:
            g.deleted("lyric_line", line)


def restore_line(db: Database, song_id: str, line_id: str) -> None:
    """Riporta riga e parole ai valori dell'analisi (le righe aggiunte vengono eliminate)."""
    with db.session() as s:
        line = _line(s, song_id, line_id)
        _restore(s, EditGroup(s, song_id), line)


def restore_all(db: Database, song_id: str) -> None:
    with db.session() as s:
        g = EditGroup(s, song_id)
        for line in s.scalars(select(LyricLine).where(LyricLine.song_id == song_id)):
            _restore(s, g, line)


def _restore(s: Session, g: EditGroup, line: LyricLine) -> None:
    if line.origin is Origin.USER:
        g.deleted("lyric_line", line)
        return
    g.update(
        "lyric_line",
        line,
        {
            "text": line.original_text or line.text,
            "start_s": line.original_start_s,
            "end_s": line.original_end_s,
            "is_deleted": False,
        },
    )
    for w in s.scalars(select(LyricWord).where(LyricWord.line_id == line.id)):
        if w.origin is Origin.USER:
            g.deleted("lyric_word", w)
        else:
            g.update(
                "lyric_word",
                w,
                {
                    "text": w.original_text or w.text,
                    "start_s": w.original_start_s,
                    "end_s": w.original_end_s,
                    "is_deleted": False,
                },
            )
