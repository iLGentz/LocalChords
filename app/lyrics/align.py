"""Allineamento parola per parola del testo di riferimento alla trascrizione di Whisper.

1. Il testo di riferimento (LRCLIB o incollato dall'utente) e le parole trascritte vengono
   normalizzati (minuscole, senza accenti né punteggiatura).
2. Allineamento globale (Needleman-Wunsch) con punteggio di somiglianza tra parole: le parole
   simili ereditano i tempi di Whisper.
3. Le parole non riconosciute ricevono tempi interpolati tra le vicine allineate, in
   proporzione alla lunghezza.
4. Se il testo ha i tempi per riga (LRC), questi fanno da ancora: le parole di una riga
   restano dentro i suoi limiti.

Senza trascrizione utilizzabile (nessun modello Whisper o voce non rilevata) le parole si
distribuiscono dentro i tempi di riga, se ci sono: è un allineamento approssimativo e
la confidenza lo segnala (0).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any

MATCH_THRESHOLD = 0.6
GAP_PENALTY = -0.45
MISMATCH_PENALTY = -0.6
DEFAULT_LAST_LINE_S = 4.0
MAX_GAP_WORD_S = 0.6
_TOKEN = re.compile(r"\S+")


@dataclass
class WordOut:
    text: str
    start_s: float | None
    end_s: float | None
    confidence: float


@dataclass
class LineOut:
    text: str
    start_s: float | None
    end_s: float | None
    words: list[WordOut] = field(default_factory=list)


@dataclass(frozen=True)
class AsrWord:
    text: str
    start: float
    end: float
    probability: float


def normalize(word: str) -> str:
    decomposed = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in decomposed if c.isalnum())


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text)


@lru_cache(maxsize=200_000)
def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def _align(ref: list[str], hyp: list[str]) -> list[int | None]:
    """Per ogni parola di riferimento, l'indice della parola trascritta associata."""
    n, m = len(ref), len(hyp)
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]  # 0 diag, 1 su (gap in hyp), 2 sinistra
    for i in range(1, n + 1):
        score[i][0] = i * GAP_PENALTY
        back[i][0] = 1
    for j in range(1, m + 1):
        score[0][j] = j * GAP_PENALTY
        back[0][j] = 2
    for i in range(1, n + 1):
        ri = ref[i - 1]
        row, prev = score[i], score[i - 1]
        for j in range(1, m + 1):
            sim = _similarity(ri, hyp[j - 1])
            diag = prev[j - 1] + (sim if sim >= MATCH_THRESHOLD else MISMATCH_PENALTY)
            up = prev[j] + GAP_PENALTY
            left = row[j - 1] + GAP_PENALTY
            if diag >= up and diag >= left:
                row[j], back[i][j] = diag, 0
            elif up >= left:
                row[j], back[i][j] = up, 1
            else:
                row[j], back[i][j] = left, 2
    mapping: list[int | None] = [None] * n
    i, j = n, m
    while i > 0 and j > 0:
        move = back[i][j]
        if move == 0:
            if _similarity(ref[i - 1], hyp[j - 1]) >= MATCH_THRESHOLD:
                mapping[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif move == 1:
            i -= 1
        else:
            j -= 1
    return mapping


def align_lines(
    lines: list[tuple[str, float | None]],
    asr: list[AsrWord],
    duration_s: float,
) -> list[LineOut]:
    """``lines``: (testo, inizio di riga o None). Restituisce righe con parole temporizzate."""
    ref_words: list[tuple[int, str]] = []  # (indice riga, parola originale)
    for li, (text, _start) in enumerate(lines):
        ref_words.extend((li, w) for w in tokenize(text))
    mapping = _align([normalize(w) for _li, w in ref_words], [normalize(a.text) for a in asr])

    # Limiti di riga dai tempi LRC (se presenti).
    bounds: list[tuple[float | None, float | None]] = []
    for li, (_text, start) in enumerate(lines):
        nxt = next((s for _t, s in lines[li + 1 :] if s is not None), None)
        end = (
            nxt if nxt is not None else (start + DEFAULT_LAST_LINE_S if start is not None else None)
        )
        bounds.append((start, min(end, duration_s) if end is not None else None))

    times: list[tuple[float | None, float | None, float]] = []
    for (li, _w), j in zip(ref_words, mapping, strict=True):
        if j is None:
            times.append((None, None, 0.0))
            continue
        a = asr[j]
        lo, hi = bounds[li]
        # Una parola trascritta fuori dalla sua riga LRC (oltre 2 s) è un falso abbinamento.
        if lo is not None and (a.end < lo - 2.0 or (hi is not None and a.start > hi + 2.0)):
            times.append((None, None, 0.0))
            continue
        sim = _similarity(normalize(_w), normalize(a.text))
        times.append((a.start, a.end, round(sim * a.probability, 3)))

    _interpolate(ref_words, times, bounds)

    out: list[LineOut] = []
    cursor = 0
    for li, (text, start) in enumerate(lines):
        words: list[WordOut] = []
        for w in tokenize(text):
            s, e, conf = times[cursor]
            words.append(WordOut(w, _r(s), _r(e), conf))
            cursor += 1
        timed = [x for x in words if x.start_s is not None]
        line_start = timed[0].start_s if timed else start
        line_end = timed[-1].end_s if timed else bounds[li][1]
        out.append(LineOut(text, _r(line_start), _r(line_end), words))
    return out


def _interpolate(
    ref_words: list[tuple[int, str]],
    times: list[tuple[float | None, float | None, float]],
    bounds: list[tuple[float | None, float | None]],
) -> None:
    """Riempie i buchi tra parole allineate, rispettando i limiti di riga quando esistono."""
    n = len(times)
    i = 0
    while i < n:
        if times[i][0] is not None:
            i += 1
            continue
        j = i
        while j < n and times[j][0] is None:
            j += 1
        li_first, li_last = ref_words[i][0], ref_words[j - 1][0]
        prev_end = times[i - 1][1] if i > 0 else None
        next_start = times[j][0] if j < n else None
        lo = bounds[li_first][0] if bounds[li_first][0] is not None else prev_end
        hi = bounds[li_last][1] if bounds[li_last][1] is not None else next_start
        if prev_end is not None and lo is not None:
            lo = max(lo, prev_end)
        if next_start is not None and hi is not None:
            hi = min(hi, next_start)
        # Ai bordi (nessuna parola allineata da un lato) le parole non si allungano a
        # riempire tutta la pausa: al massimo MAX_GAP_WORD_S ciascuna.
        count = j - i
        same_line_next = j < n and ref_words[j][0] == li_last
        same_line_prev = i > 0 and ref_words[i - 1][0] == li_first
        if lo is not None and hi is not None:
            if not same_line_next:
                hi = min(hi, lo + MAX_GAP_WORD_S * count)
            elif not same_line_prev:
                lo = max(lo, hi - MAX_GAP_WORD_S * count)
        if lo is None or hi is None or hi <= lo:
            i = j
            continue
        weights = [max(len(normalize(ref_words[k][1])), 1) for k in range(i, j)]
        total = float(sum(weights))
        t = lo
        for k, w in zip(range(i, j), weights, strict=True):
            span = (hi - lo) * w / total
            times[k] = (t, t + span * 0.9, 0.0)
            t += span
        i = j


def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def lines_from_transcription(asr_segments: list[dict[str, Any]]) -> list[LineOut]:
    """Senza testo di riferimento: ogni segmento di Whisper diventa una riga."""
    out: list[LineOut] = []
    for seg in asr_segments:
        raw_words = seg.get("words") or []
        words = [
            WordOut(
                str(w["word"]).strip(),
                _r(float(w["start"])),
                _r(float(w["end"])),
                round(float(w.get("probability", 0.0)), 3),
            )
            for w in raw_words
            if str(w["word"]).strip()
        ]
        text = " ".join(w.text for w in words) or str(seg.get("text", "")).strip()
        if not text:
            continue
        out.append(
            LineOut(
                text,
                words[0].start_s if words else _r(float(seg["start"])),
                words[-1].end_s if words else _r(float(seg["end"])),
                words,
            )
        )
    return out
