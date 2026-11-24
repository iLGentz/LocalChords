"""Processo figlio per Whisper: ``python -m app.lyrics.runner download|transcribe``.

Come per la separazione, il worker lo controlla da fuori (avanzamento su stderr nel formato
``NN%|``, esito JSON sull'ultima riga di stdout) e lo termina in caso di annullamento.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def _cuda_dlls() -> None:
    """CTranslate2 su CUDA cerca cuBLAS e cuDNN: le DLL incluse in PyTorch CUDA bastano."""
    try:
        import torch

        lib = Path(torch.__file__).parent / "lib"
        if lib.is_dir() and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(lib))
    except ImportError:
        pass


def _load_16k_mono(path: str) -> Any:
    """Audio mono a 16 kHz come lo vuole Whisper.

    Lo decodifichiamo noi (soundfile + librosa) invece di lasciarlo a faster-whisper: il suo
    decoder usa PyAV con un'opzione (``metadata_errors``) rimossa nelle versioni recenti.
    """
    import librosa
    import numpy as np
    import soundfile as sf

    data, sr = sf.read(path, dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if sr != 16000:
        mono = librosa.resample(mono, orig_sr=sr, target_sr=16000)
    return np.ascontiguousarray(mono, dtype=np.float32)


def _progress(fraction: float) -> None:
    sys.stderr.write(f"{min(max(int(fraction * 100), 0), 100)}%|\n")
    sys.stderr.flush()


def _cmd_download(ns: argparse.Namespace) -> dict[str, Any]:
    from faster_whisper import download_model

    download_model(ns.alias, output_dir=ns.model_dir)
    return {"ok": True}


def _cmd_transcribe(ns: argparse.Namespace) -> dict[str, Any]:
    if ns.device == "cuda":
        _cuda_dlls()
    from faster_whisper import WhisperModel

    model = WhisperModel(
        ns.model_dir,
        device=ns.device,
        compute_type=ns.compute_type,
        cpu_threads=ns.threads,
        local_files_only=True,
    )
    segments, info = model.transcribe(
        _load_16k_mono(ns.audio),
        language=ns.language or None,
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
        condition_on_previous_text=False,
    )
    duration = float(info.duration or 0.0)
    out: list[dict[str, Any]] = []
    for seg in segments:
        words = [
            {
                "start": round(float(w.start), 3),
                "end": round(float(w.end), 3),
                "word": w.word,
                "probability": round(float(w.probability), 3),
            }
            for w in (seg.words or [])
        ]
        out.append(
            {
                "start": round(float(seg.start), 3),
                "end": round(float(seg.end), 3),
                "text": seg.text.strip(),
                "no_speech_prob": round(float(seg.no_speech_prob), 3),
                "words": words,
            }
        )
        if duration > 0:
            _progress(float(seg.end) / duration)
    return {
        "ok": True,
        "language": info.language,
        "language_probability": round(float(info.language_probability), 3),
        "duration": duration,
        "segments": out,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.lyrics.runner")
    sub = parser.add_subparsers(dest="cmd", required=True)
    dl = sub.add_parser("download")
    dl.add_argument("--alias", required=True)
    dl.add_argument("--model-dir", required=True)
    tr = sub.add_parser("transcribe")
    tr.add_argument("--model-dir", required=True)
    tr.add_argument("--audio", required=True)
    tr.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    tr.add_argument("--compute-type", default="int8")
    tr.add_argument("--threads", type=int, default=0)
    tr.add_argument("--language", default="")
    ns = parser.parse_args(argv)
    try:
        result = _cmd_download(ns) if ns.cmd == "download" else _cmd_transcribe(ns)
    except ImportError:
        result = {
            "ok": False,
            "code": "whisper_missing",
            "error": "faster-whisper non è installato: riesegui setup.ps1.",
        }
    except Exception as exc:
        text = str(exc)
        oom = "out of memory" in text.lower()
        result = {
            "ok": False,
            "code": "out_of_memory" if oom else "transcription_failed",
            "error": "Memoria insufficiente per la trascrizione: prova con la CPU."
            if oom
            else f"Trascrizione non riuscita: {text[:300]}",
        }
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
