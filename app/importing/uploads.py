"""Upload in due passi: ricezione con anteprima dei metadati, poi conferma.

Il file caricato resta in ``data/uploads/<upload_id>/`` con un ``meta.json`` finché
l'utente non conferma (diventa un brano) o annulla. Le anteprime abbandonate vengono
eliminate all'avvio dopo ``UPLOAD_MAX_AGE_S``.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.db.base import new_id, utcnow
from app.errors import AppError
from app.importing.validation import check_extension, check_probe, guess_metadata
from app.media.ffmpeg import MediaError, MediaTools
from app.storage.files import Storage, remove_tree, safe_filename

log = logging.getLogger(__name__)

UPLOAD_MAX_AGE_S = 24 * 3600
META_FILE = "meta.json"


class PendingUpload(BaseModel):
    upload_id: str
    filename: str
    stored_name: str
    extension: str
    size_bytes: int
    checksum_sha256: str
    probe: dict[str, Any]
    title: str
    artist: str | None
    album: str | None
    created_at: datetime


class UploadService:
    def __init__(self, settings: Settings, storage: Storage) -> None:
        self.settings = settings
        self.storage = storage

    @property
    def max_bytes(self) -> int:
        return self.settings.max_upload_mb * 1024 * 1024

    async def receive(
        self, chunks: AsyncIterator[bytes], filename: str, content_length: int | None
    ) -> PendingUpload:
        filename = safe_filename(filename)
        ext = check_extension(filename)
        if content_length is not None and content_length > self.max_bytes:
            raise self._too_large(content_length)
        tools = MediaTools.from_settings(self.settings)

        upload_id = new_id()
        directory = self.storage.upload_dir(upload_id)
        directory.mkdir(parents=True)
        stored_name = "source" + ext
        target = directory / stored_name
        digest = hashlib.sha256()
        size = 0
        try:
            with target.open("wb") as fh:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise self._too_large(size)
                    digest.update(chunk)
                    fh.write(chunk)
            if size == 0:
                raise MediaError("empty_file", "Il file è vuoto.")
            probe = await run_in_threadpool(tools.probe, target)
            check_probe(probe)
            guessed = guess_metadata(probe.tags, filename)
            pending = PendingUpload(
                upload_id=upload_id,
                filename=filename,
                stored_name=stored_name,
                extension=ext,
                size_bytes=size,
                checksum_sha256=digest.hexdigest(),
                probe=probe.to_dict(),
                title=guessed.title,
                artist=guessed.artist,
                album=guessed.album,
                created_at=utcnow(),
            )
            (directory / META_FILE).write_text(pending.model_dump_json(), "utf-8")
        except BaseException:
            remove_tree(directory)
            raise
        log.info(
            "upload ricevuto",
            extra={"upload_id": upload_id, "size": size, "format": probe.format_name},
        )
        return pending

    def get(self, upload_id: str) -> PendingUpload:
        try:
            meta = self.storage.upload_dir(upload_id) / META_FILE
            return PendingUpload.model_validate_json(meta.read_text("utf-8"))
        except (ValueError, OSError) as exc:
            raise AppError(
                "upload_not_found",
                "Il file caricato non è più disponibile: caricalo di nuovo.",
            ) from exc

    def discard(self, upload_id: str) -> None:
        with contextlib.suppress(ValueError):  # id non valido: niente da rimuovere
            remove_tree(self.storage.upload_dir(upload_id))

    def _too_large(self, size: int) -> MediaError:
        return MediaError(
            "file_too_large",
            f"Il file è troppo grande ({size / 1024 / 1024:.0f} MB). "
            f"Il limite è {self.settings.max_upload_mb} MB (LOCALCHORDS_MAX_UPLOAD_MB).",
            {"size_bytes": size, "max_bytes": self.max_bytes},
        )
