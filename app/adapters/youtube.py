"""Adapter YouTube basato su yt-dlp. Opzionale e **disattivato di default**.

Attivazione: ``LOCALCHORDS_YOUTUBE_ENABLED=true`` e installazione dell'extra con
``setup.ps1 -YouTube`` (installa yt-dlp e Deno, il runtime JavaScript che yt-dlp richiede
per YouTube). Non aggira DRM né restrizioni: niente cookie, niente account, i video privati,
con limiti d'età o bloccati per paese restituiscono un errore esplicito.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.config import Settings
from app.errors import AppError

log = logging.getLogger(__name__)

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}

ProgressFn = Callable[[float], None]


@dataclass(frozen=True)
class VideoInfo:
    video_id: str
    url: str
    title: str
    artist: str | None
    album: str | None
    duration_s: float | None


def canonical_url(raw: str) -> str:
    """Valida un link YouTube e lo riduce alla forma canonica ``watch?v=<id>``."""
    raw = raw.strip()
    if not raw:
        raise _invalid()
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parsed = urlparse(raw)
    except ValueError as exc:
        raise _invalid() from exc
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or host not in _HOSTS:
        raise _invalid()
    video_id: str | None = None
    parts = [p for p in parsed.path.split("/") if p]
    if host == "youtu.be":
        video_id = parts[0] if parts else None
    elif parts[:1] == ["watch"] or not parts:
        values = parse_qs(parsed.query).get("v", [])
        video_id = values[0] if values else None
    elif parts[0] in ("shorts", "embed", "live", "v") and len(parts) > 1:
        video_id = parts[1]
    if video_id is None or not _VIDEO_ID.match(video_id):
        raise _invalid()
    return f"https://www.youtube.com/watch?v={video_id}"


class YouTubeAdapter:
    def __init__(self, settings: Settings) -> None:
        if not settings.youtube_enabled:
            raise AppError(
                "youtube_disabled",
                "L'import da YouTube è disattivato. Si attiva con "
                "LOCALCHORDS_YOUTUBE_ENABLED=true nelle impostazioni.",
            )
        try:
            import yt_dlp
        except ImportError as exc:
            raise AppError(
                "youtube_not_installed",
                "Il componente per YouTube non è installato: esegui setup.ps1 -YouTube.",
            ) from exc
        self._yt_dlp: Any = yt_dlp
        self.settings = settings
        # Deno (installato come pacchetto Python) sta accanto all'interprete: lo rendiamo
        # trovabile da yt-dlp anche quando l'app è avviata senza venv attivo.
        scripts = str(Path(sys.executable).parent)
        if scripts not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = scripts + os.pathsep + os.environ.get("PATH", "")

    def _options(self, **extra: Any) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
            "cachedir": False,
            "socket_timeout": 30,
            "retries": 3,
            "logger": _QuietLogger(),
        }
        ffmpeg = self.settings.resolve_ffmpeg()
        if ffmpeg is not None:
            opts["ffmpeg_location"] = str(ffmpeg.parent)
        opts.update(extra)
        return opts

    def preview(self, url: str) -> VideoInfo:
        url = canonical_url(url)
        info = self._extract(url, download=False)
        if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
            raise AppError("live_not_supported", "Le dirette non si possono importare.")
        return VideoInfo(
            video_id=str(info.get("id", "")),
            url=url,
            title=str(info.get("track") or info.get("title") or "Senza titolo")[:500],
            artist=_opt_str(info.get("artist") or info.get("creator") or info.get("uploader")),
            album=_opt_str(info.get("album")),
            duration_s=_opt_float(info.get("duration")),
        )

    def download(
        self,
        url: str,
        dest_dir: Path,
        on_progress: ProgressFn,
        should_stop: Callable[[], None],
    ) -> Path:
        """Scarica la migliore traccia audio disponibile in ``dest_dir/original.<ext>``."""
        url = canonical_url(url)
        dest_dir.mkdir(parents=True, exist_ok=True)

        def hook(status: dict[str, Any]) -> None:
            should_stop()
            if status.get("status") == "downloading":
                total = status.get("total_bytes") or status.get("total_bytes_estimate")
                done = status.get("downloaded_bytes") or 0
                if total:
                    on_progress(min(float(done) / float(total), 1.0))

        opts = self._options(
            format="bestaudio[ext=m4a]/bestaudio/best",
            outtmpl=str(dest_dir / "original.%(ext)s"),
            progress_hooks=[hook],
        )
        try:
            info = self._extract(url, download=True, opts=opts)
        except BaseException:
            for partial in dest_dir.glob("original.*"):
                partial.unlink(missing_ok=True)
            raise
        files = [p for p in dest_dir.glob("original.*") if not p.name.endswith(".part")]
        if not files:
            raise AppError("download_failed", "Il download non ha prodotto alcun file audio.")
        log.info("download completato", extra={"video_id": info.get("id"), "file": files[0].name})
        return files[0]

    def _extract(
        self, url: str, *, download: bool, opts: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        yt_dlp = self._yt_dlp
        try:
            with yt_dlp.YoutubeDL(opts or self._options()) as ydl:
                info = ydl.extract_info(url, download=download)
        except yt_dlp.utils.DownloadError as exc:
            raise _map_error(str(exc)) from exc
        if not isinstance(info, dict):
            raise AppError("video_unavailable", "Informazioni sul video non disponibili.")
        return info


class _QuietLogger:
    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)

    def error(self, msg: str) -> None:
        log.info("yt-dlp: %s", msg)


def _map_error(message: str) -> AppError:
    text = message.lower()
    rules: list[tuple[tuple[str, ...], str, str]] = [
        (("private video",), "video_private", "Il video è privato."),
        (
            ("sign in to confirm your age", "age-restricted", "inappropriate for some users"),
            "video_age_restricted",
            "Il video ha limiti d'età e non si può scaricare senza account.",
        ),
        (
            ("not available in your country", "geo restrict", "blocked it in your country"),
            "video_geo_blocked",
            "Il video non è disponibile nel tuo paese.",
        ),
        (
            (
                "video unavailable",
                "this video is not available",
                "has been removed",
                "does not exist",
            ),
            "video_unavailable",
            "Il video non è disponibile o è stato rimosso.",
        ),
        (
            ("javascript runtime", "js runtime", "deno"),
            "youtube_runtime_missing",
            "Manca il runtime JavaScript richiesto da yt-dlp: riesegui setup.ps1 -YouTube.",
        ),
        (
            ("unable to download webpage", "timed out", "getaddrinfo", "connection"),
            "network_error",
            "Connessione a YouTube non riuscita: controlla la rete e riprova.",
        ),
    ]
    for needles, code, text_it in rules:
        if any(n in text for n in needles):
            return AppError(code, text_it)
    return AppError(
        "download_failed", "Download da YouTube non riuscito.", {"yt_dlp": message[-400:]}
    )


def _invalid() -> AppError:
    return AppError(
        "invalid_url",
        "Link non valido: incolla l'indirizzo di un video YouTube "
        "(youtube.com/watch?v=… oppure youtu.be/…).",
    )


def _opt_str(value: Any) -> str | None:
    return str(value)[:500] if value else None


def _opt_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
