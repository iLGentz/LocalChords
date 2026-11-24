"""Sezioni del brano (backend librosa con euristiche sulle ripetizioni).

1. Feature per beat: chroma (armonia) e MFCC (timbro), standardizzate.
2. Matrice di auto-somiglianza e curva di novità con kernel a scacchiera (Foote):
   i picchi sono i confini candidati, distanti almeno 4 battute, agganciati al downbeat.
3. Etichette per ripetizione: segmenti con andamento armonico simile ricevono la stessa
   lettera (A, B, C, ...).
4. Nomi: Intro e Outro ai bordi se brevi; Ritornello la lettera ripetuta più energica;
   Strofa la lettera ripetuta che compare prima; Bridge un segmento unico nella seconda
   metà; le altre "Sezione X". Tutti i nomi sono modificabili.

SongFormer (profilo di qualità massima) potrà sostituire questo backend.
"""

from __future__ import annotations

import itertools
from collections import Counter
from dataclasses import asdict, dataclass

import librosa
import numpy as np
import numpy.typing as npt

from app.analysis.beats import BeatGrid
from app.analysis.features import Features, beat_sync

MIN_SEGMENT_BARS = 4
SIMILARITY_SAME_LABEL = 0.80

COLORS = {
    "Intro": "#7c8aa5",
    "Strofa": "#4f9d8f",
    "Ritornello": "#f0a73a",
    "Bridge": "#b07cc6",
    "Outro": "#7c8aa5",
}
OTHER_COLORS = ["#d9776b", "#6b9bd9", "#a3b05b", "#c98a5a", "#5bb0a3"]


@dataclass(frozen=True)
class SectionData:
    name: str
    color: str
    start_s: float
    end_s: float
    label: str


def detect_sections(f: Features, grid: BeatGrid) -> list[SectionData]:
    n_beats = len(grid.times)
    bar_len = grid.beats_per_bar
    if n_beats < bar_len * MIN_SEGMENT_BARS * 2:
        return [SectionData("Brano", COLORS["Strofa"], 0.0, round(f.duration_s, 3), "A")]

    frames = librosa.time_to_frames(np.array(grid.times), sr=f.sr, hop_length=f.hop).astype(
        np.int64
    )
    chroma = beat_sync(f.chroma, frames, f.chroma.shape[1]).astype(np.float64)
    mfcc = beat_sync(f.mfcc, frames, f.mfcc.shape[1]).astype(np.float64)
    rms = beat_sync(f.rms[np.newaxis, :], frames, len(f.rms))[0].astype(np.float64)
    feats = np.vstack([_standardize(chroma), 0.7 * _standardize(mfcc[1:])])

    boundaries = _boundaries(feats, grid, MIN_SEGMENT_BARS * bar_len)
    segments = list(itertools.pairwise(boundaries))
    labels = _labels(chroma, segments)
    names = _names(segments, labels, rms, n_beats, bar_len)

    end_time = f.duration_s
    sections: list[SectionData] = []
    palette = iter(OTHER_COLORS * 4)
    other_color: dict[str, str] = {}
    for idx, ((a, _b), label, name) in enumerate(zip(segments, labels, names, strict=True)):
        start = 0.0 if idx == 0 else grid.times[a]
        stop = end_time if idx == len(segments) - 1 else grid.times[segments[idx + 1][0]]
        color = COLORS.get(name) or other_color.setdefault(label, next(palette))
        sections.append(SectionData(name, color, round(start, 3), round(stop, 3), label))
    return sections


def _standardize(x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    z = (x - x.mean(axis=1, keepdims=True)) / (x.std(axis=1, keepdims=True) + 1e-9)
    return np.asarray(z, dtype=np.float64)


def _boundaries(feats: npt.NDArray[np.float64], grid: BeatGrid, min_gap: int) -> list[int]:
    n = feats.shape[1]
    norm = feats / (np.linalg.norm(feats, axis=0, keepdims=True) + 1e-9)
    ssm = norm.T @ norm
    half = min(16, n // 4)
    kernel = _checkerboard(half)
    padded = np.pad(ssm, half, mode="edge")
    novelty = np.array(
        [float(np.sum(padded[i : i + 2 * half, i : i + 2 * half] * kernel)) for i in range(n)]
    )
    novelty = np.clip(novelty, 0, None)
    if novelty.max() > 0:
        novelty /= novelty.max()

    # Picchi in ordine di forza, a distanza minima, sopra una soglia adattiva.
    threshold = float(np.median(novelty) + 0.5 * np.std(novelty))
    chosen: list[int] = []
    for i in np.argsort(novelty)[::-1]:
        if novelty[i] < threshold:
            break
        if i < min_gap or n - i < min_gap:
            continue
        if all(abs(int(i) - c) >= min_gap for c in chosen):
            chosen.append(int(i))
    snapped = sorted({_snap_to_downbeat(c, grid.downbeats) for c in chosen})
    result = [0]
    for b in snapped:
        if b - result[-1] >= min_gap // 2 and n - b >= min_gap // 2:
            result.append(b)
    return [*result, n]


def _checkerboard(half: int) -> npt.NDArray[np.float64]:
    sign = np.ones((2 * half, 2 * half))
    sign[:half, half:] = -1
    sign[half:, :half] = -1
    g = np.exp(-0.5 * (np.linspace(-2, 2, 2 * half) ** 2))
    return np.asarray(sign * np.outer(g, g), dtype=np.float64)


def _snap_to_downbeat(index: int, downbeats: list[bool]) -> int:
    for delta in range(0, 3):
        for cand in (index - delta, index + delta):
            if 0 <= cand < len(downbeats) and downbeats[cand]:
                return cand
    return index


def _labels(chroma: npt.NDArray[np.float64], segments: list[tuple[int, int]]) -> list[str]:
    """Stessa lettera ai segmenti con andamento armonico simile (chroma ricampionato)."""
    profiles: list[npt.NDArray[np.float64]] = []
    for a, b in segments:
        seg = chroma[:, a:b]
        idx = np.linspace(0, seg.shape[1] - 1, 16).round().astype(int)
        vec = seg[:, idx].flatten()
        profiles.append(vec / (np.linalg.norm(vec) + 1e-9))
    labels: list[str] = []
    reps: list[tuple[str, npt.NDArray[np.float64]]] = []
    for vec in profiles:
        best = max(reps, key=lambda r: float(r[1] @ vec), default=None)
        if best is not None and float(best[1] @ vec) >= SIMILARITY_SAME_LABEL:
            labels.append(best[0])
        else:
            letter = chr(ord("A") + len(reps)) if len(reps) < 26 else "Z"
            reps.append((letter, vec))
            labels.append(letter)
    return labels


def _names(
    segments: list[tuple[int, int]],
    labels: list[str],
    rms: npt.NDArray[np.float64],
    n_beats: int,
    bar_len: int,
) -> list[str]:
    counts = Counter(labels)
    energy = {
        lab: float(
            np.mean(
                [rms[a:b].mean() for (a, b), l2 in zip(segments, labels, strict=True) if l2 == lab]
            )
        )
        for lab in counts
    }
    repeated = [lab for lab in counts if counts[lab] > 1]
    chorus = max(repeated, key=lambda lab: energy[lab], default=None)
    verse = next((lab for lab in labels if lab in repeated and lab != chorus), None)
    mean_energy = float(rms.mean())

    names: list[str] = []
    for idx, ((a, b), lab) in enumerate(zip(segments, labels, strict=True)):
        bars = (b - a) / bar_len
        quiet = float(rms[a:b].mean()) < mean_energy
        if idx == 0 and bars <= 8 and counts[lab] == 1 and (quiet or len(segments) > 3):
            names.append("Intro")
        elif idx == len(segments) - 1 and bars <= 8 and counts[lab] == 1:
            names.append("Outro")
        elif lab == chorus:
            names.append("Ritornello")
        elif lab == verse:
            names.append("Strofa")
        elif counts[lab] == 1 and a > n_beats / 2:
            names.append("Bridge")
        else:
            names.append(f"Sezione {lab}")
    return names


def to_dicts(sections: list[SectionData]) -> list[dict[str, object]]:
    return [asdict(s) for s in sections]
