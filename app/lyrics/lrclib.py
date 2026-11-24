"""Client LRCLIB (https://lrclib.net): testi sincronizzati per riga, gratuiti e senza chiave.

Facoltativo (``LOCALCHORDS_LRCLIB_ENABLED``). Si inviano solo titolo, artista, album e
durata; nessun audio e nessun dato dell'utente. User-Agent generico, come chiede il
servizio, senza informazioni sul PC.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from app import __version__

log = logging.getLogger(__name__)

BASE_URL = "https://lrclib.net/api"
TIMEOUT_S = 15
DURATION_TOLERANCE_S = 4.0
_USER_AGENT = f"LocalChords/{__version__}"


@dataclass(frozen=True)
class LrcLine:
    start_s: float | None
    text: str


@dataclass(frozen=True)
class LyricsResult:
    lines: list[LrcLine]
    synced: bool
    instrumental: bool
    source_id: int | None


_TIME_TAG = re.compile(r"\[(\d{1,3}):(\d{1,2}(?:[.:]\d{1,3})?)\]")
_META_TAG = re.compile(r"^\[[a-zA-Z]+:.*\]$")


def parse_lrc(text: str) -> list[LrcLine]:
    """Righe LRC ``[mm:ss.xx] testo`` (anche più tag per riga), ordinate per tempo."""
    lines: list[LrcLine] = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw or _META_TAG.match(raw):
            continue
        tags = _TIME_TAG.findall(raw)
        content = _TIME_TAG.sub("", raw).strip()
        if not tags:
            lines.append(LrcLine(None, content))
            continue
        for minutes, seconds in tags:
            start = int(minutes) * 60 + float(seconds.replace(":", "."))
            lines.append(LrcLine(round(start, 3), content))
    timed = [ln for ln in lines if ln.start_s is not None]
    if timed and len(timed) == len(lines):
        lines.sort(key=lambda ln: ln.start_s or 0.0)
    return lines


def plain_lines(text: str) -> list[LrcLine]:
    return [LrcLine(None, ln.strip()) for ln in text.splitlines() if ln.strip()]


def _get(path: str, params: dict[str, str]) -> Any:
    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def _to_result(record: dict[str, Any]) -> LyricsResult | None:
    if record.get("instrumental"):
        return LyricsResult([], False, True, record.get("id"))
    synced = record.get("syncedLyrics")
    if synced:
        lines = [ln for ln in parse_lrc(synced) if ln.text or ln.start_s is not None]
        if lines:
            return LyricsResult(lines, True, False, record.get("id"))
    plain = record.get("plainLyrics")
    if plain:
        return LyricsResult(plain_lines(plain), False, False, record.get("id"))
    return None


def fetch(
    title: str, artist: str | None, album: str | None, duration_s: float | None
) -> LyricsResult | None:
    """Cerca il testo: prima corrispondenza esatta, poi ricerca filtrata per durata.

    Restituisce None se non trovato. Gli errori di rete sono sollevati (OSError)."""
    if artist:
        params = {"track_name": title, "artist_name": artist}
        if album:
            params["album_name"] = album
        if duration_s:
            params["duration"] = str(round(duration_s))
        record = _get("/get", params)
        if isinstance(record, dict):
            result = _to_result(record)
            if result is not None:
                return result

    query = {"track_name": title}
    if artist:
        query["artist_name"] = artist
    candidates = _get("/search", query) or []
    if not isinstance(candidates, list):
        return None

    def score(rec: dict[str, Any]) -> tuple[int, float]:
        dur = rec.get("duration")
        diff = abs(float(dur) - duration_s) if dur and duration_s else 999.0
        return (0 if rec.get("syncedLyrics") else 1, diff)

    for rec in sorted((c for c in candidates if isinstance(c, dict)), key=score):
        dur = rec.get("duration")
        if duration_s and dur and abs(float(dur) - duration_s) > DURATION_TOLERANCE_S:
            continue
        result = _to_result(rec)
        if result is not None:
            return result
    return None
