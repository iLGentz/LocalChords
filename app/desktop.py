"""Avvio dell'app desktop: migrazioni, API in un thread, worker in un processo separato,
finestra nativa pywebview (Edge WebView2).

``python -m app`` oppure ``LocalChords.bat``. Opzione ``--smoke-test``: apre la finestra,
verifica che l'interfaccia si carichi, chiude e restituisce 0 se tutto è andato bene.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import IO, Any

import uvicorn

from app.config import Settings, get_settings
from app.db.migrate import upgrade_to_head
from app.logging_setup import configure_logging

log = logging.getLogger("app.desktop")

WINDOW_TITLE = "LocalChords"
WINDOW_SIZE = (1440, 900)
WINDOW_MIN_SIZE = (1280, 760)
BACKGROUND = "#1c1a18"
STARTUP_TIMEOUT_S = 30.0
WORKER_STOP_TIMEOUT_S = 10.0


# ----------------------------------------------------------- singola istanza


class InstanceLock:
    """Lock su file (msvcrt) per evitare due server e due worker sullo stesso database."""

    def __init__(self, data_dir: Path) -> None:
        self.lock_path = data_dir / "instance.lock"
        self.info_path = data_dir / "instance.json"
        self._fh: IO[bytes] | None = None

    def acquire(self) -> bool:
        fh = open(self.lock_path, "a+b")  # noqa: SIM115 - resta aperto per tutta la vita
        try:
            if sys.platform == "win32":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            fh.close()
            return False
        self._fh = fh
        return True

    def write_info(self, url: str) -> None:
        self.info_path.write_text(json.dumps({"url": url, "pid": os.getpid()}), "utf-8")

    def running_url(self) -> str | None:
        try:
            data = json.loads(self.info_path.read_text("utf-8"))
        except (OSError, ValueError):
            return None
        url = data.get("url")
        return url if isinstance(url, str) else None

    def release(self) -> None:
        if self._fh is None:
            return
        with contextlib.suppress(OSError):
            self.info_path.unlink(missing_ok=True)
        if sys.platform == "win32":
            import msvcrt

            with contextlib.suppress(OSError):
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        self._fh.close()
        self._fh = None


# ------------------------------------------------------------------ servizi


def pick_port(host: str, preferred: int) -> int:
    """Usa la porta preferita se libera, altrimenti una porta libera qualsiasi."""
    for port in ([preferred] if preferred else []) + [0]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            chosen: int = sock.getsockname()[1]
            return chosen
    raise RuntimeError("Nessuna porta TCP libera")


class ApiThread:
    def __init__(self, host: str, port: int) -> None:
        config = uvicorn.Config(
            "app.api.main:create_app",
            factory=True,
            host=host,
            port=port,
            log_config=None,
            access_log=False,
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, name="api", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)


def start_worker() -> subprocess.Popen[bytes]:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.Popen(
        [sys.executable, "-m", "app.worker", "--watch-stdin"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )


def stop_worker(proc: subprocess.Popen[bytes]) -> None:
    """Chiusura ordinata: chiudendo lo stdin il worker rimette in coda il job corrente."""
    if proc.poll() is not None:
        return
    with contextlib.suppress(OSError):
        if proc.stdin is not None:
            proc.stdin.close()
    try:
        proc.wait(timeout=WORKER_STOP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        log.warning("worker non si è chiuso in tempo: terminato")
        proc.kill()
        proc.wait(timeout=5)


def wait_for_health(url: str, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.2)
    return False


_interactive = True


def show_error(message: str) -> None:
    log.error(message)
    if sys.platform == "win32" and _interactive:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, WINDOW_TITLE, 0x10)
    else:  # pragma: no cover
        print(message, file=sys.stderr)


# ------------------------------------------------------------------ finestra


def open_window(url: str, settings: Settings, smoke_test: bool) -> bool:
    """Apre la finestra e blocca fino alla sua chiusura. In smoke test restituisce se
    l'interfaccia React si è montata."""
    import webview

    window = webview.create_window(
        WINDOW_TITLE,
        url,
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=WINDOW_MIN_SIZE,
        background_color=BACKGROUND,
    )
    assert window is not None
    result: dict[str, Any] = {"ok": not smoke_test}

    def _smoke() -> None:
        deadline = time.monotonic() + STARTUP_TIMEOUT_S
        try:
            while time.monotonic() < deadline:
                mounted = window.evaluate_js("document.querySelector('[data-app-ready]') !== null")
                if mounted:
                    result["ok"] = True
                    break
                time.sleep(0.3)
        finally:
            log.info("smoke test finestra", extra={"ok": result["ok"]})
            window.destroy()

    # pywebview blocca i download per impostazione predefinita: servono per gli export.
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.start(
        _smoke if smoke_test else None,
        private_mode=False,
        storage_path=str(settings.data_dir / "webview"),
    )
    return bool(result["ok"])


# --------------------------------------------------------------------- main


def _ensure_std_streams() -> None:
    """Con pythonw.exe stdout e stderr sono None: alcune librerie ci scrivono comunque."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="localchords")
    parser.add_argument("--smoke-test", action="store_true", help="apre, verifica e chiude")
    args = parser.parse_args(argv)

    global _interactive
    _interactive = not args.smoke_test
    _ensure_std_streams()
    settings = get_settings()
    settings.ensure_dirs()
    configure_logging(settings.logs_dir, "app", settings.log_level.value)

    lock = InstanceLock(settings.data_dir)
    if not lock.acquire():
        url = lock.running_url()
        if url and wait_for_health(url, 3):
            log.info("istanza già attiva: apro un'altra finestra", extra={"url": url})
            return 0 if open_window(url, settings, args.smoke_test) else 1
        show_error("LocalChords è già in esecuzione ma non risponde. Chiudilo e riprova.")
        return 1

    api: ApiThread | None = None
    worker: subprocess.Popen[bytes] | None = None
    try:
        upgrade_to_head(settings.database_url)
        port = pick_port(settings.host, settings.port)
        url = f"http://{settings.host}:{port}"
        api = ApiThread(settings.host, port)
        api.start()
        worker = start_worker()
        if not wait_for_health(url, STARTUP_TIMEOUT_S):
            show_error("Il server interno non è partito. Controlla logs/app.log.")
            return 1
        lock.write_info(url)
        log.info("app avviata", extra={"url": url, "worker_pid": worker.pid})
        ok = open_window(url, settings, args.smoke_test)
        return 0 if ok else 1
    except Exception as exc:
        log.exception("avvio non riuscito")
        show_error(f"Avvio non riuscito: {exc}. Dettagli in logs/app.log.")
        return 1
    finally:
        if worker is not None:
            stop_worker(worker)
        if api is not None:
            api.stop()
        lock.release()
        log.info("app chiusa")


if __name__ == "__main__":
    sys.exit(main())
