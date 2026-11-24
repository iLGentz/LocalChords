"""Occupazione su disco per categoria e per brano, più pulizia selettiva."""

from __future__ import annotations

import contextlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.storage.files import Storage, remove_tree

CATEGORIES = ("audio", "stems", "waveforms", "cache", "uploads", "models", "exports")
CLEANABLE = ("cache", "uploads", "exports")


@dataclass(frozen=True)
class SongUsage:
    song_id: str
    audio: int
    stems: int
    waveforms: int

    @property
    def total(self) -> int:
        return self.audio + self.stems + self.waveforms


def dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            with contextlib.suppress(OSError):
                total += (Path(root) / name).stat().st_size
    return total


def category_sizes(storage: Storage, database: Path) -> dict[str, int]:
    sizes = {name: dir_size(storage.root / name) for name in CATEGORIES}
    sizes["database"] = sum(
        p.stat().st_size
        for p in (database, database.with_name(database.name + "-wal"))
        if p.is_file()
    )
    return sizes


def song_usage(storage: Storage, song_ids: list[str]) -> list[SongUsage]:
    return [
        SongUsage(
            song_id=sid,
            audio=dir_size(storage.root / "audio" / sid),
            stems=dir_size(storage.root / "stems" / sid),
            waveforms=dir_size(storage.root / "waveforms" / sid),
        )
        for sid in song_ids
    ]


def disk_free(path: Path) -> tuple[int, int]:
    usage = shutil.disk_usage(path)
    return usage.free, usage.total


def cleanup(storage: Storage, targets: list[str]) -> int:
    """Svuota le categorie richieste (solo quelle ricostruibili). Restituisce i byte liberati."""
    freed = 0
    for target in targets:
        if target not in CLEANABLE:
            raise ValueError(f"Categoria non pulibile: {target}")
        directory = storage.root / target
        freed += dir_size(directory)
        remove_tree(directory)
        directory.mkdir(parents=True, exist_ok=True)
    return freed
