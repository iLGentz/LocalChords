"""Caricamento audio e feature condivise tra le fasi dell'analisi (calcolate una volta)."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import librosa
import numpy as np
import numpy.typing as npt
import soundfile as sf

FloatArray = npt.NDArray[np.float32]

SR = 22050
HOP = 512


def load_mono(paths: list[Path], sr: int = SR) -> FloatArray:
    """Carica e somma uno o più file (es. più stem) in un segnale mono a ``sr``."""
    total: FloatArray | None = None
    for path in paths:
        data, file_sr = sf.read(str(path), dtype="float32", always_2d=True)
        mono = data.mean(axis=1).astype(np.float32)
        if file_sr != sr:
            mono = librosa.resample(mono, orig_sr=file_sr, target_sr=sr).astype(np.float32)
        if total is None:
            total = mono
        else:
            n = min(len(total), len(mono))
            total = total[:n] + mono[:n]
    if total is None:
        raise ValueError("Nessun file audio da caricare")
    peak = float(np.max(np.abs(total))) if total.size else 0.0
    return total / peak if peak > 1.0 else total


@dataclass
class Features:
    """Feature calcolate pigramente su segnale mono a 22 050 Hz, hop 512 (~23 ms)."""

    y: FloatArray
    sr: int = SR
    hop: int = HOP
    _cache: dict[str, FloatArray] = field(default_factory=dict, repr=False)

    @property
    def duration_s(self) -> float:
        return len(self.y) / self.sr

    @cached_property
    def harmonic(self) -> FloatArray:
        return librosa.effects.harmonic(self.y, margin=3.0).astype(np.float32)

    @cached_property
    def onset_env(self) -> FloatArray:
        env = librosa.onset.onset_strength(y=self.y, sr=self.sr, hop_length=self.hop)
        return np.asarray(env, dtype=np.float32)

    @cached_property
    def low_onset_env(self) -> FloatArray:
        """Onset nella banda bassa (cassa e basso): indizio per il primo battito."""
        env = librosa.onset.onset_strength(
            y=self.y, sr=self.sr, hop_length=self.hop, fmax=200.0, n_mels=32
        )
        return np.asarray(env, dtype=np.float32)

    @cached_property
    def chroma(self) -> FloatArray:
        """Chroma CQT sulla componente armonica (più robusto alle percussioni)."""
        c = librosa.feature.chroma_cqt(
            y=self.harmonic, sr=self.sr, hop_length=self.hop, bins_per_octave=36, n_octaves=6
        )
        return np.asarray(c, dtype=np.float32)

    @cached_property
    def bass_chroma(self) -> FloatArray:
        """Chroma delle sole ottave basse (circa 32-260 Hz), per il basso dell'accordo."""
        c = librosa.feature.chroma_cqt(
            y=self.harmonic,
            sr=self.sr,
            hop_length=self.hop,
            fmin=float(librosa.note_to_hz("C1")),
            n_octaves=3,
            bins_per_octave=36,
        )
        return np.asarray(c, dtype=np.float32)

    @cached_property
    def mfcc(self) -> FloatArray:
        m = librosa.feature.mfcc(y=self.y, sr=self.sr, hop_length=self.hop, n_mfcc=13)
        return np.asarray(m, dtype=np.float32)

    @cached_property
    def rms(self) -> FloatArray:
        r = librosa.feature.rms(y=self.y, hop_length=self.hop)[0]
        return np.asarray(r, dtype=np.float32)

    def time_to_frame(self, t: float) -> int:
        return round(t * self.sr / self.hop)


def beat_sync(feature: FloatArray, beat_frames: npt.NDArray[np.int64], n_frames: int) -> FloatArray:
    """Media per intervallo tra beat consecutivi (un vettore per beat)."""
    bounds = np.concatenate([beat_frames, [n_frames]]).astype(np.int64)
    out = np.zeros((feature.shape[0], len(beat_frames)), dtype=np.float32)
    for i in range(len(beat_frames)):
        a = int(min(bounds[i], feature.shape[1] - 1))
        b = int(max(min(bounds[i + 1], feature.shape[1]), a + 1))
        out[:, i] = feature[:, a:b].mean(axis=1)
    return out
