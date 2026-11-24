"""Wrapper tipizzati per ffprobe e ffmpeg (processi esterni, senza finestra di console)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import Settings
from app.errors import AppError

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
PROBE_TIMEOUT_S = 60
_MAX_VOLUME_RE = re.compile(r"max_volume:\s*(-?\d+(?:\.\d+)?|-inf)\s*dB")


class MediaError(AppError):
    """Errore nella lettura o conversione di un file audio."""


@dataclass(frozen=True)
class AudioStream:
    codec: str
    sample_rate: int | None
    channels: int | None


@dataclass(frozen=True)
class ProbeResult:
    format_name: str
    duration_s: float | None
    size_bytes: int | None
    audio: AudioStream | None
    tags: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_name": self.format_name,
            "duration_s": self.duration_s,
            "size_bytes": self.size_bytes,
            "audio": None
            if self.audio is None
            else {
                "codec": self.audio.codec,
                "sample_rate": self.audio.sample_rate,
                "channels": self.audio.channels,
            },
            "tags": self.tags,
        }


@dataclass(frozen=True)
class TranscodeResult:
    max_volume_db: float | None
    """Picco del segnale in dBFS (``-inf`` diventa -200). None se non misurato."""


ProgressFn = Callable[[float, float | None], None]
"""(frazione 0..1, velocità rispetto al tempo reale)."""


class MediaTools:
    def __init__(self, ffmpeg: Path, ffprobe: Path) -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

    @classmethod
    def from_settings(cls, settings: Settings) -> MediaTools:
        ffmpeg = settings.resolve_ffmpeg()
        ffprobe = settings.resolve_ffprobe()
        if ffmpeg is None or ffprobe is None:
            raise MediaError(
                "ffmpeg_missing",
                "FFmpeg non è installato. Esegui setup.ps1 oppure indica il percorso in "
                "LOCALCHORDS_FFMPEG_PATH.",
            )
        return cls(ffmpeg, ffprobe)

    # ------------------------------------------------------------------ probe

    def probe(self, path: Path) -> ProbeResult:
        try:
            proc = subprocess.run(
                [
                    str(self.ffprobe),
                    "-v",
                    "error",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    str(path),
                ],
                capture_output=True,
                timeout=PROBE_TIMEOUT_S,
                creationflags=_NO_WINDOW,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise MediaError("invalid_audio", "Il file non si riesce a leggere (timeout).") from exc
        if proc.returncode != 0:
            raise MediaError(
                "invalid_audio",
                "Il file è danneggiato o non è un file audio leggibile.",
                {"ffprobe": _tail(proc.stderr)},
            )
        try:
            data = json.loads(proc.stdout.decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise MediaError("invalid_audio", "Risposta di ffprobe non valida.") from exc

        fmt: dict[str, Any] = data.get("format") or {}
        streams: list[dict[str, Any]] = data.get("streams") or []
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        audio = None
        if audio_streams:
            first = audio_streams[0]
            audio = AudioStream(
                codec=str(first.get("codec_name", "sconosciuto")),
                sample_rate=_to_int(first.get("sample_rate")),
                channels=_to_int(first.get("channels")),
            )
        tags: dict[str, str] = {}
        for source in [fmt.get("tags") or {}] + [s.get("tags") or {} for s in audio_streams[:1]]:
            for key, value in source.items():
                tags.setdefault(str(key).lower(), str(value))
        duration = _to_float(fmt.get("duration"))
        if duration is None and audio_streams:
            duration = _to_float(audio_streams[0].get("duration"))
        return ProbeResult(
            format_name=str(fmt.get("format_name", "")),
            duration_s=duration,
            size_bytes=_to_int(fmt.get("size")),
            audio=audio,
            tags=tags,
        )

    # ------------------------------------------------------------- transcode

    def transcode_to_flac(
        self,
        src: Path,
        dst: Path,
        *,
        duration_s: float | None,
        sample_rate: int = 44100,
        on_progress: ProgressFn | None = None,
        should_stop: Callable[[], None] | None = None,
    ) -> TranscodeResult:
        """Converte la prima traccia audio in FLAC stereo 16 bit e misura il picco.

        ``should_stop`` viene chiamata periodicamente e può sollevare un'eccezione
        (annullamento): in quel caso il processo ffmpeg viene terminato e il file parziale
        rimosso. La scrittura avviene su un file temporaneo rinominato solo alla fine.
        """
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.stem + ".part" + dst.suffix)
        cmd = [
            str(self.ffmpeg),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            str(src),
            "-map",
            "0:a:0",
            "-vn",
            "-af",
            "volumedetect",
            "-ac",
            "2",
            "-ar",
            str(sample_rate),
            "-sample_fmt",
            "s16",
            "-c:a",
            "flac",
            "-progress",
            "pipe:1",
            "-nostats",
            str(tmp),
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_NO_WINDOW,
        )
        stderr_chunks: list[bytes] = []
        reader = threading.Thread(
            target=lambda: stderr_chunks.append(proc.stderr.read() if proc.stderr else b""),
            daemon=True,
        )
        reader.start()
        started = time.monotonic()
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                if should_stop is not None:
                    should_stop()
                line = raw.decode("ascii", errors="ignore").strip()
                if line.startswith("out_time_us=") and on_progress and duration_s:
                    out_us = _to_float(line.split("=", 1)[1])
                    if out_us is not None and out_us >= 0:
                        done_s = out_us / 1_000_000
                        elapsed = max(time.monotonic() - started, 1e-3)
                        on_progress(min(done_s / duration_s, 1.0), done_s / elapsed)
            proc.wait()
        except BaseException:
            proc.kill()
            proc.wait()
            tmp.unlink(missing_ok=True)
            raise
        finally:
            reader.join(timeout=5)

        stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")
        if proc.returncode != 0:
            tmp.unlink(missing_ok=True)
            raise MediaError(
                "conversion_failed",
                "La conversione dell'audio non è riuscita: il file potrebbe essere danneggiato.",
                {"ffmpeg": _tail(stderr.encode())},
            )
        tmp.replace(dst)
        return TranscodeResult(max_volume_db=_parse_max_volume(stderr))


def _parse_max_volume(stderr: str) -> float | None:
    match = _MAX_VOLUME_RE.search(stderr)
    if match is None:
        return None
    value = match.group(1)
    return -200.0 if value == "-inf" else float(value)


def _tail(data: bytes, limit: int = 600) -> str:
    text = data.decode("utf-8", errors="replace").strip()
    return text[-limit:]


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
