"""Beat grid, primo battito della battuta e BPM con confidenza (backend librosa).

Metodo:
- beat: ``librosa.beat.beat_track`` (programmazione dinamica sull'onset strength);
- BPM: dalla mediana degli intervalli tra beat, più stabile del tempo globale;
- downbeat: in 4/4, tra le 4 fasi possibili si sceglie quella i cui beat hanno più energia
  nella banda bassa (cassa, basso) e più cambi armonici;
- confidenza: regolarità degli intervalli e forza della pulsazione sui beat.

È il backend "leggero" previsto dal piano; Beat This! (più accurato) arriva con la gestione
dei modelli nella fase 4.
"""

from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np

from app.analysis.features import Features, beat_sync

BEATS_PER_BAR = 4
MIN_BEATS = 8


@dataclass(frozen=True)
class BeatGrid:
    times: list[float]
    downbeats: list[bool]
    bars: list[int | None]
    bpm: float | None
    bpm_confidence: float
    beats_per_bar: int

    def to_dict(self) -> dict[str, object]:
        return {
            "times": self.times,
            "downbeats": self.downbeats,
            "bars": self.bars,
            "bpm": self.bpm,
            "bpm_confidence": self.bpm_confidence,
            "beats_per_bar": self.beats_per_bar,
        }


def detect_beats(f: Features) -> BeatGrid:
    _tempo, frames = librosa.beat.beat_track(
        onset_envelope=f.onset_env, sr=f.sr, hop_length=f.hop, trim=False, units="frames"
    )
    frames = np.asarray(frames, dtype=np.int64)
    if len(frames) < MIN_BEATS:
        return BeatGrid([], [], [], None, 0.0, BEATS_PER_BAR)

    times = librosa.frames_to_time(frames, sr=f.sr, hop_length=f.hop)
    ibi = np.diff(times)
    median_ibi = float(np.median(ibi))
    bpm = 60.0 / median_ibi if median_ibi > 0 else None

    # Confidenza: regolarità (coefficiente di variazione) e pulsazione sui beat.
    cv = float(np.std(ibi) / np.mean(ibi)) if np.mean(ibi) > 0 else 1.0
    regularity = float(np.clip(1.0 - cv * 4.0, 0.0, 1.0))
    env = f.onset_env
    pulse = float(np.mean(env[np.clip(frames, 0, len(env) - 1)]) / (np.mean(env) + 1e-9))
    pulse_score = float(np.clip((pulse - 1.0) / 1.5, 0.0, 1.0))
    confidence = round(0.6 * regularity + 0.4 * pulse_score, 3)

    phase = _downbeat_phase(f, frames)
    downbeats = [(i - phase) % BEATS_PER_BAR == 0 for i in range(len(frames))]
    # Battute numerate da 1; i beat prima del primo downbeat (anacrusi) stanno nella battuta 0.
    bars: list[int | None] = []
    bar = 0
    for is_down in downbeats:
        if is_down:
            bar += 1
        bars.append(bar)
    return BeatGrid(
        times=[round(float(t), 4) for t in times],
        downbeats=downbeats,
        bars=bars,
        bpm=round(bpm, 2) if bpm else None,
        bpm_confidence=confidence,
        beats_per_bar=BEATS_PER_BAR,
    )


def _downbeat_phase(f: Features, frames: np.ndarray) -> int:
    low = f.low_onset_env
    low_at = low[np.clip(frames, 0, len(low) - 1)]
    chroma = beat_sync(f.chroma, frames, f.chroma.shape[1])
    norm = chroma / (np.linalg.norm(chroma, axis=0, keepdims=True) + 1e-9)
    change = np.concatenate([[0.0], 1.0 - np.sum(norm[:, 1:] * norm[:, :-1], axis=0)])

    def z(x: np.ndarray) -> np.ndarray:
        return np.asarray((x - x.mean()) / (x.std() + 1e-9), dtype=np.float64)

    score = z(low_at.astype(np.float64)) + z(change.astype(np.float64))
    phases = [float(np.mean(score[p::BEATS_PER_BAR])) for p in range(BEATS_PER_BAR)]
    return int(np.argmax(phases))
