"""Audio sintetico con risultato noto, per verificare analisi e pipeline senza canzoni reali.

Progressione in Do maggiore, 4/4, un accordo per battuta, con:
- accordo tenuto (fondamentale, terza, quinta su due ottave, con armonici),
- basso sulla fondamentale,
- cassa su ogni battito (più forte sul primo) e charleston sui contrattempi.
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
NOTE = {
    "C": 0,
    "C#": 1,
    "D": 2,
    "D#": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "G": 7,
    "G#": 8,
    "A": 9,
    "A#": 10,
    "B": 11,
}
QUALITY = {"": (0, 4, 7), "m": (0, 3, 7)}


def _midi_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _tone(freq: float, n: int, amp: float) -> np.ndarray:
    t = np.arange(n) / SR
    wave = sum((0.6**k) * np.sin(2 * math.pi * freq * (k + 1) * t) for k in range(4))
    env = np.minimum(1.0, np.arange(n) / (0.01 * SR)) * np.exp(-t * 0.6)
    return amp * wave * env


def _kick(n: int, amp: float) -> np.ndarray:
    t = np.arange(n) / SR
    freq = 50 + 90 * np.exp(-t * 30)
    return amp * np.sin(2 * math.pi * np.cumsum(freq) / SR) * np.exp(-t * 18)


def _hat(n: int, amp: float, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(n) / SR
    return amp * rng.standard_normal(n) * np.exp(-t * 60)


def progression(
    chords: list[str], bpm: float = 120.0, repeats: int = 4, lead_in_s: float = 0.0
) -> tuple[np.ndarray, list[tuple[float, float, str]]]:
    """Restituisce (audio stereo float32, [(inizio, fine, accordo)])."""
    rng = np.random.default_rng(0)
    beat = 60.0 / bpm
    bar = 4 * beat
    seq = chords * repeats
    total = lead_in_s + bar * len(seq) + 1.0
    out = np.zeros(int(total * SR), dtype=np.float64)
    truth = []
    for i, name in enumerate(seq):
        root_name = name.rstrip("m") if name.endswith("m") else name
        quality = "m" if name.endswith("m") else ""
        root = NOTE[root_name]
        start = lead_in_s + i * bar
        s0, n = int(start * SR), int(bar * SR)
        for interval in QUALITY[quality]:
            for octave in (60, 72):
                out[s0 : s0 + n] += _tone(_midi_hz(octave + root + interval), n, 0.06)
        out[s0 : s0 + n] += _tone(_midi_hz(36 + root), n, 0.18)
        for b in range(4):
            bs = int((start + b * beat) * SR)
            kn = int(0.25 * SR)
            out[bs : bs + kn] += _kick(kn, 0.9 if b == 0 else 0.55)
            hs = int((start + (b + 0.5) * beat) * SR)
            hn = int(0.05 * SR)
            out[hs : hs + hn] += _hat(hn, 0.15, rng)
        truth.append((start, start + bar, name))
    out /= np.max(np.abs(out)) * 1.1
    stereo = np.stack([out, out], axis=1).astype(np.float32)
    return stereo, truth


def write_progression(path: Path, **kwargs: object) -> list[tuple[float, float, str]]:
    audio, truth = progression(**kwargs)  # type: ignore[arg-type]
    sf.write(str(path), audio, SR)
    return truth


def speech_wav(path: Path, text: str) -> bool:
    """Voce sintetica con la sintesi vocale di Windows (System.Speech). False se non disponibile."""
    if sys.platform != "win32":
        return False
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.Rate = -1; "
        f"$s.SetOutputToWaveFile('{path}'); "
        f"$s.Speak('{text}'); $s.Dispose()"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        timeout=120,
        check=False,
    )
    return proc.returncode == 0 and path.is_file() and path.stat().st_size > 10_000
