"""Regole di validazione dell'audio importato e ricavo dei metadati."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.media.ffmpeg import MediaError, ProbeResult

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".mp3": "MP3",
    ".wav": "WAV",
    ".m4a": "M4A",
    ".flac": "FLAC",
    ".ogg": "OGG",
}
# Nomi di formato di ffprobe ammessi per i file caricati (``format_name`` è un elenco
# separato da virgole, es. "mov,mp4,m4a,3gp,3g2,mj2").
_FILE_FORMATS = {"mp3", "wav", "mp4", "m4a", "flac", "ogg"}
# Per i download da YouTube si accettano anche WebM/Opus.
_DOWNLOAD_FORMATS = _FILE_FORMATS | {"webm", "matroska", "aac"}

MIN_DURATION_S = 3.0
MAX_DURATION_S = 60 * 60.0
SILENCE_THRESHOLD_DB = -60.0


def check_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise MediaError(
            "unsupported_format",
            f"Formato non supportato ({ext or 'senza estensione'}). "
            f"Formati ammessi: {', '.join(SUPPORTED_EXTENSIONS.values())}.",
        )
    return ext


def check_probe(probe: ProbeResult, *, downloaded: bool = False) -> None:
    """Verifica formato, presenza di una traccia audio e durata."""
    allowed = _DOWNLOAD_FORMATS if downloaded else _FILE_FORMATS
    names = {n.strip() for n in probe.format_name.split(",")}
    if not names & allowed:
        raise MediaError(
            "unsupported_format",
            "Il contenuto del file non corrisponde a un formato audio supportato "
            f"(rilevato: {probe.format_name or 'sconosciuto'}).",
        )
    if probe.audio is None:
        raise MediaError("no_audio_track", "Il file non contiene una traccia audio.")
    if probe.duration_s is None:
        raise MediaError("invalid_audio", "Impossibile determinare la durata del file.")
    if probe.duration_s < MIN_DURATION_S:
        raise MediaError(
            "audio_too_short",
            f"Il brano dura meno di {MIN_DURATION_S:.0f} secondi: troppo poco da analizzare.",
        )
    if probe.duration_s > MAX_DURATION_S:
        raise MediaError(
            "audio_too_long",
            f"Il brano dura più di {MAX_DURATION_S / 60:.0f} minuti: non è supportato.",
        )


def check_not_silent(max_volume_db: float | None) -> None:
    if max_volume_db is not None and max_volume_db <= SILENCE_THRESHOLD_DB:
        raise MediaError(
            "audio_silent",
            "L'audio è silenzioso o quasi: non ci sono tracce sufficienti da analizzare.",
            {"max_volume_db": max_volume_db},
        )


@dataclass(frozen=True)
class GuessedMetadata:
    title: str
    artist: str | None
    album: str | None


# Separatori ammessi tra artista e titolo: trattino, en dash, em dash.
_DASHES = "-" + chr(0x2013) + chr(0x2014)
_SPLIT_ARTIST_TITLE = re.compile(
    rf"^\s*(?P<artist>[^{_DASHES}]+?)\s+[{_DASHES}]\s+(?P<title>.+?)\s*$"
)
_TRACK_PREFIX = re.compile(r"^\s*\d{1,3}\s*[-._)]\s*")
_NOISE = re.compile(
    r"\s*[\(\[](?:official|lyric|audio|video|hd|hq|4k|remaster)[^\)\]]*[\)\]]", re.IGNORECASE
)


def guess_metadata(tags: dict[str, str], filename: str) -> GuessedMetadata:
    """Titolo, artista e album dai tag; se mancano, dal nome del file ("Artista - Titolo")."""
    title = _clean(tags.get("title"))
    artist = _clean(tags.get("artist")) or _clean(tags.get("album_artist"))
    album = _clean(tags.get("album"))
    if not title:
        stem = _TRACK_PREFIX.sub("", Path(filename).stem.replace("_", " "))
        stem = _NOISE.sub("", stem).strip()
        match = _SPLIT_ARTIST_TITLE.match(stem)
        if match and not artist:
            artist = match.group("artist").strip()
            title = match.group("title").strip()
        else:
            title = stem
    return GuessedMetadata(title=(title or "Senza titolo")[:500], artist=artist, album=album)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value[:500] or None
