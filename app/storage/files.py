"""Gestione della cartella ``data/``.

Struttura:
    data/uploads/<upload_id>/          file caricati in attesa di conferma (anteprima)
    data/audio/<song_id>/original.ext  file originale importato
    data/audio/<song_id>/audio.flac    audio normalizzato (44,1 kHz, stereo, 16 bit)
    data/stems/<song_id>/              stem (fase 4)
    data/waveforms/<song_id>/          picchi per la waveform (fase 3)

Nel database i percorsi sono relativi a ``data/`` (POSIX), così la cartella si può spostare.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import time
from pathlib import Path, PurePosixPath

log = logging.getLogger(__name__)

NORMALIZED_NAME = "audio.flac"
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_HEX_ID = re.compile(r"^[0-9a-f]{32}$")


class Storage:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir.resolve()

    # ----------------------------------------------------------------- cartelle

    @property
    def uploads_dir(self) -> Path:
        return self.root / "uploads"

    def upload_dir(self, upload_id: str) -> Path:
        return self.uploads_dir / _checked_id(upload_id)

    def song_audio_dir(self, song_id: str) -> Path:
        return self.root / "audio" / _checked_id(song_id)

    def song_dirs(self, song_id: str) -> list[Path]:
        sid = _checked_id(song_id)
        return [self.root / sub / sid for sub in ("audio", "stems", "waveforms")]

    # ----------------------------------------------------------------- percorsi

    def to_relative(self, path: Path) -> str:
        return PurePosixPath(path.resolve().relative_to(self.root)).as_posix()

    def to_absolute(self, relative: str) -> Path:
        path = (self.root / PurePosixPath(relative)).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"Percorso fuori dalla cartella dati: {relative}")
        return path

    # ----------------------------------------------------------------- pulizia

    def delete_song_files(self, song_id: str) -> None:
        for directory in self.song_dirs(song_id):
            remove_tree(directory)

    def cleanup_uploads(self, max_age_s: float) -> int:
        """Elimina le anteprime di upload abbandonate. Restituisce quante ne ha rimosse."""
        if not self.uploads_dir.is_dir():
            return 0
        now = time.time()
        removed = 0
        for entry in self.uploads_dir.iterdir():
            if entry.is_dir() and now - entry.stat().st_mtime > max_age_s:
                remove_tree(entry)
                removed += 1
        return removed


def remove_tree(path: Path) -> None:
    """Rimozione tollerante: su Windows un file può restare aperto per qualche istante."""
    for attempt in range(5):
        if not path.exists():
            return
        try:
            shutil.rmtree(path)
            return
        except OSError:
            if attempt == 4:
                log.warning("cartella non rimossa", extra={"path": str(path)})
                return
            time.sleep(0.2 * (attempt + 1))


def safe_filename(name: str, default: str = "audio") -> str:
    """Nome file sicuro per Windows, senza percorso."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = _UNSAFE_CHARS.sub("_", base).strip(" .")
    return base[:150] or default


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _checked_id(value: str) -> str:
    if not _HEX_ID.match(value):
        raise ValueError(f"Identificativo non valido: {value!r}")
    return value
