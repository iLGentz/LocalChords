"""Picchi della waveform, letti a blocchi dal FLAC normalizzato (memoria costante).

Salvati in ``data/waveforms/<song_id>/peaks.json``: un valore 0..1 (massimo assoluto del
mono) ogni 1/``PEAKS_PER_SECOND`` secondi. Il frontend li passa a Wavesurfer, che così non
deve decodificare l'audio per disegnarla.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

PEAKS_PER_SECOND = 50


def compute_peaks(audio_path: Path, out_path: Path) -> dict[str, float | int]:
    info = sf.info(str(audio_path))
    bucket = max(int(info.samplerate // PEAKS_PER_SECOND), 1)
    peaks: list[float] = []
    for block in sf.blocks(
        str(audio_path), blocksize=bucket * 1024, dtype="float32", always_2d=True
    ):
        mono = np.abs(block).max(axis=1)
        usable = len(mono) - len(mono) % bucket
        if usable:
            peaks.extend(mono[:usable].reshape(-1, bucket).max(axis=1).tolist())
        if len(mono) > usable:
            peaks.append(float(mono[usable:].max()))
    top = max(peaks, default=0.0) or 1.0
    data = {
        "version": 1,
        "duration_s": round(info.frames / info.samplerate, 4),
        "peaks_per_second": info.samplerate / bucket,
        "peaks": [round(p / top, 3) for p in peaks],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".part")
    tmp.write_text(json.dumps(data, separators=(",", ":")), "utf-8")
    tmp.replace(out_path)
    return {"count": len(peaks), "duration_s": data["duration_s"]}
