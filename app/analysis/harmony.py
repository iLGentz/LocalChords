"""Accordi e tonalità (backend chroma + HMM, il "fallback" del piano).

Accordi:
1. chroma CQT della componente armonica, mediato tra beat consecutivi (un vettore per beat);
2. punteggio contro i modelli di 9 qualità per 12 fondamentali, con un bonus se il basso
   suona la fondamentale e una penalità a priori per le qualità complesse;
3. Viterbi (HMM con alta probabilità di restare sullo stesso accordo) per una sequenza
   stabile allineata alla beat grid;
4. accordi consecutivi uguali uniti in eventi; rivolto (``C/E``) se il basso suona con
   decisione un'altra nota dell'accordo.

Tonalità: correlazione del chroma complessivo con i profili di Krumhansl-Kessler, combinata
con la quota di durata degli accordi diatonici in ciascuna tonalità.

Accuratezza attesa più bassa di BTC (modello neurale previsto per il profilo di qualità
massima): va verificata su brani reali e l'editor resta essenziale.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import librosa
import numpy as np
import numpy.typing as npt

from app.analysis.beats import BeatGrid
from app.analysis.features import Features, beat_sync
from app.analysis.theory import (
    NO_CHORD,
    QUALITIES,
    Quality,
    chord_name,
    is_diatonic,
    key_name,
)

SOFTMAX_BETA = 14.0
P_STAY = 0.82
BASS_BONUS = 0.10
QUIET_RATIO = 0.08  # sotto questa frazione dell'energia mediana il beat è "senza accordo"

# Profili di Krumhansl-Kessler (C maggiore, C minore).
_KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


@dataclass(frozen=True)
class ChordEventData:
    start_s: float
    end_s: float
    chord: str
    confidence: float
    beat_position: int


@dataclass(frozen=True)
class KeyResult:
    key: str | None
    confidence: float


def _templates() -> tuple[npt.NDArray[np.float64], list[tuple[int, Quality]]]:
    rows: list[npt.NDArray[np.float64]] = []
    labels: list[tuple[int, Quality]] = []
    for quality in QUALITIES:
        for root in range(12):
            vec = np.zeros(12)
            for interval, weight in zip(quality.intervals, quality.weights, strict=True):
                vec[(root + interval) % 12] = weight
            rows.append(vec / np.linalg.norm(vec))
            labels.append((root, quality))
    return np.vstack(rows), labels


def detect_chords(f: Features, grid: BeatGrid) -> list[ChordEventData]:
    if len(grid.times) < 2:
        return []
    frames = librosa.time_to_frames(np.array(grid.times), sr=f.sr, hop_length=f.hop).astype(
        np.int64
    )
    n_frames = f.chroma.shape[1]
    chroma = beat_sync(f.chroma, frames, n_frames).astype(np.float64)
    bass = beat_sync(f.bass_chroma, frames, n_frames).astype(np.float64)
    rms = beat_sync(f.rms[np.newaxis, :], frames, len(f.rms))[0].astype(np.float64)

    chroma_n = chroma / (np.linalg.norm(chroma, axis=0, keepdims=True) + 1e-9)
    bass_n = bass / (bass.max(axis=0, keepdims=True) + 1e-9)
    templates, labels = _templates()

    scores = templates @ chroma_n  # (n_chords, n_beats)
    priors = np.array([q.prior for _, q in labels])[:, np.newaxis]
    roots = np.array([r for r, _ in labels])
    scores = scores - priors + BASS_BONUS * bass_n[roots, :]

    quiet = rms < QUIET_RATIO * (np.median(rms) + 1e-9)
    no_chord = np.where(quiet, 1.0, 0.2)[np.newaxis, :]
    all_scores = np.vstack([scores, no_chord])

    probs = np.exp(SOFTMAX_BETA * (all_scores - all_scores.max(axis=0, keepdims=True)))
    probs /= probs.sum(axis=0, keepdims=True)
    transition = librosa.sequence.transition_loop(all_scores.shape[0], P_STAY)
    path = np.asarray(librosa.sequence.viterbi(probs, transition), dtype=np.int64)

    times = grid.times
    last_ibi = times[-1] - times[-2]
    end_time = min(times[-1] + last_ibi, f.duration_s)
    events: list[ChordEventData] = []
    start = 0
    for i in range(1, len(path) + 1):
        if i < len(path) and path[i] == path[start]:
            continue
        state = int(path[start])
        beats = slice(start, i)
        confidence = float(np.mean(probs[state, beats]))
        if state == len(labels):
            name = NO_CHORD
        else:
            root, quality = labels[state]
            name = chord_name(root, quality, _slash_bass(bass_n[:, beats], root, quality))
        events.append(
            ChordEventData(
                start_s=round(times[start], 4),
                end_s=round(times[i] if i < len(times) else end_time, 4),
                chord=name,
                confidence=round(confidence, 3),
                beat_position=start,
            )
        )
        start = i
    return events


def _slash_bass(bass: npt.NDArray[np.float64], root: int, quality: Quality) -> int | None:
    """Nota del basso se è un'altra nota dell'accordo, nettamente più forte della fondamentale."""
    profile = bass.mean(axis=1)
    note = int(np.argmax(profile))
    chord_tones = {(root + i) % 12 for i in quality.intervals}
    if note == root or note not in chord_tones:
        return None
    if profile[note] < 0.6 or profile[note] < 1.4 * profile[root]:
        return None
    return note


def detect_key(f: Features, chords: list[ChordEventData]) -> KeyResult:
    profile = f.chroma.astype(np.float64).sum(axis=1)
    if not np.any(profile):
        return KeyResult(None, 0.0)
    candidates: list[tuple[float, int, bool]] = []
    parsed = [_parse(c) for c in chords]
    total = sum(c.end_s - c.start_s for c, p in zip(chords, parsed, strict=True) if p) or 1.0
    for minor, base in ((False, _KK_MAJOR), (True, _KK_MINOR)):
        for tonic in range(12):
            corr = float(np.corrcoef(profile, np.roll(base, tonic))[0, 1])
            diatonic = sum(
                c.end_s - c.start_s
                for c, p in zip(chords, parsed, strict=True)
                if p and is_diatonic(p[0], p[1], tonic, minor)
            )
            candidates.append((0.6 * corr + 0.4 * diatonic / total, tonic, minor))
    candidates.sort(reverse=True)
    best, second = candidates[0], candidates[1]
    margin = best[0] - second[0]
    confidence = float(np.clip(margin / 0.12, 0.0, 1.0) * np.clip(best[0] / 0.8, 0.0, 1.0))
    return KeyResult(key_name(best[1], best[2]), round(confidence, 3))


def _parse(event: ChordEventData) -> tuple[int, Quality] | None:
    if event.chord == NO_CHORD:
        return None
    name = event.chord.split("/")[0]
    root_len = 2 if len(name) > 1 and name[1] == "#" else 1
    root = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B").index(name[:root_len])
    suffix = name[root_len:]
    for quality in QUALITIES:
        if quality.suffix == suffix:
            return root, quality
    return None


def to_dicts(events: list[ChordEventData]) -> list[dict[str, object]]:
    return [asdict(e) for e in events]
