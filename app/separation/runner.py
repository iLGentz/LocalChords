"""Separazione e download dei modelli in un processo figlio.

Il processo figlio (``python -m app.separation.runner ...``) carica torch e audio-separator;
il worker lo controlla da fuori: legge l'avanzamento dalle barre tqdm su stderr e lo termina
subito in caso di annullamento o di chiusura dell'app. L'ultima riga di stdout è un JSON
con l'esito.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.errors import AppError

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_PERCENT = re.compile(rb"(\d{1,3})%\|")


def run_child(
    args: list[str],
    *,
    cpu_only: bool,
    on_progress: Callable[[float], None],
    should_stop: Callable[[], None],
    cpu_threads: int = 0,
    module: str = "app.separation.runner",
) -> dict[str, Any]:
    """Esegue il runner e restituisce il JSON finale. ``should_stop`` può sollevare
    un'eccezione: il processo figlio viene terminato e l'eccezione propagata."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    if cpu_only:
        env["CUDA_VISIBLE_DEVICES"] = ""
    if cpu_threads > 0:
        for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS"):
            env[var] = str(cpu_threads)
    proc = subprocess.Popen(
        [sys.executable, "-m", module, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        creationflags=_NO_WINDOW,
    )
    stdout_lines: list[bytes] = []
    stderr_tail = bytearray()
    latest: list[float] = []

    def read_stdout() -> None:
        assert proc.stdout is not None
        stdout_lines.extend(proc.stdout.readlines())

    def read_stderr() -> None:
        assert proc.stderr is not None
        while chunk := proc.stderr.read1(4096):  # type: ignore[attr-defined]
            stderr_tail.extend(chunk)
            del stderr_tail[:-8000]
            matches = _PERCENT.findall(chunk)
            if matches:
                latest.append(int(matches[-1]) / 100.0)

    threads = [
        threading.Thread(target=read_stdout, daemon=True),
        threading.Thread(target=read_stderr, daemon=True),
    ]
    for t in threads:
        t.start()
    try:
        while proc.poll() is None:
            should_stop()
            if latest:
                on_progress(min(latest[-1], 1.0))
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=0.5)
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    finally:
        for t in threads:
            t.join(timeout=5)

    result: dict[str, Any] | None = None
    for line in reversed(stdout_lines):
        try:
            parsed = json.loads(line.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        if isinstance(parsed, dict):
            result = parsed
            break
    if result is None or not result.get("ok"):
        message = (result or {}).get("error") or "Il processo di separazione si è interrotto."
        raise AppError(
            (result or {}).get("code") or "separation_failed",
            str(message),
            {"stderr": bytes(stderr_tail[-1500:]).decode("utf-8", errors="replace")},
        )
    return result


# ---------------------------------------------------------- processo figlio


def _separator(model_dir: Path, output_dir: Path | None) -> Any:
    from audio_separator.separator import Separator

    return Separator(
        log_level=logging.WARNING,
        model_file_dir=str(model_dir),
        output_dir=str(output_dir) if output_dir else None,
        output_format="FLAC",
    )


def _cmd_download(ns: argparse.Namespace) -> dict[str, Any]:
    sep = _separator(Path(ns.model_dir), None)
    if hasattr(sep, "download_model_files"):
        sep.download_model_files(ns.model_file)
    else:  # versioni senza download separato: il caricamento scarica i file
        sep.load_model(model_filename=ns.model_file)
    return {"ok": True}


def _cmd_separate(ns: argparse.Namespace) -> dict[str, Any]:
    out = Path(ns.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    sep = _separator(Path(ns.model_dir), out)
    sep.load_model(model_filename=ns.model_file)
    files = sep.separate(ns.input)
    paths = [str(p if Path(p).is_absolute() else out / p) for p in files]
    import torch

    return {"ok": True, "files": paths, "cuda": bool(torch.cuda.is_available())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.separation.runner")
    sub = parser.add_subparsers(dest="cmd", required=True)
    dl = sub.add_parser("download")
    dl.add_argument("--model-file", required=True)
    dl.add_argument("--model-dir", required=True)
    sp = sub.add_parser("separate")
    sp.add_argument("--model-file", required=True)
    sp.add_argument("--model-dir", required=True)
    sp.add_argument("--input", required=True)
    sp.add_argument("--output-dir", required=True)
    ns = parser.parse_args(argv)
    try:
        result = _cmd_download(ns) if ns.cmd == "download" else _cmd_separate(ns)
    except ImportError:
        result = {
            "ok": False,
            "code": "separation_runtime_missing",
            "error": "Il runtime di separazione non è installato: riesegui setup.ps1.",
        }
    except MemoryError:
        result = {
            "ok": False,
            "code": "out_of_memory",
            "error": "Memoria insufficiente per la separazione: prova il profilo Leggero.",
        }
    except Exception as exc:
        text = str(exc)
        oom = "out of memory" in text.lower()
        result = {
            "ok": False,
            "code": "out_of_memory" if oom else "separation_failed",
            "error": (
                "Memoria della GPU insufficiente: prova con la CPU o il profilo Leggero."
                if oom
                else f"Separazione non riuscita: {text[:300]}"
            ),
        }
    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
