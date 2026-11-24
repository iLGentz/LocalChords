"""Catalogo dei brani: creazione da upload o da URL, ricerca, eliminazione, nuovo tentativo."""

from __future__ import annotations

import logging
import shutil

from sqlalchemy import delete, or_, select

from app.db.base import new_id
from app.db.models import (
    RUNNING_JOB_STATUSES,
    AssetKind,
    AudioAsset,
    Job,
    JobStatus,
    Song,
    SongStatus,
    SourceType,
    Stem,
)
from app.db.session import Database
from app.errors import AppError
from app.importing.uploads import PendingUpload, UploadService
from app.storage.files import Storage, remove_tree
from app.worker.queue import JobQueue

log = logging.getLogger(__name__)

IMPORT_FILE = "import_file"
IMPORT_URL = "import_url"
ANALYZE = "analyze"
SEPARATE = "separate"
DOWNLOAD_MODEL = "download_model"
ACTIVE_JOB_STATUSES = RUNNING_JOB_STATUSES | {JobStatus.QUEUED}


class SongService:
    def __init__(self, db: Database, storage: Storage, queue: JobQueue) -> None:
        self.db = db
        self.storage = storage
        self.queue = queue

    # ------------------------------------------------------------ lettura

    def list_songs(self, query: str | None = None, limit: int = 200) -> list[Song]:
        stmt = select(Song).order_by(Song.created_at.desc()).limit(limit)
        if query and query.strip():
            pattern = f"%{_escape_like(query.strip())}%"
            stmt = stmt.where(
                or_(
                    Song.title.ilike(pattern, escape="\\"),
                    Song.artist.ilike(pattern, escape="\\"),
                    Song.album.ilike(pattern, escape="\\"),
                )
            )
        with self.db.read_session() as s:
            return list(s.scalars(stmt))

    def get(self, song_id: str) -> Song:
        with self.db.read_session() as s:
            song = s.get(Song, song_id)
        if song is None:
            raise AppError("song_not_found", "Brano non trovato.")
        return song

    def latest_jobs(self, song_ids: list[str]) -> dict[str, Job]:
        """L'ultimo job di ciascun brano (per mostrare stato, progresso ed errore)."""
        if not song_ids:
            return {}
        with self.db.read_session() as s:
            rows = s.scalars(
                select(Job)
                .where(Job.song_id.in_(song_ids))
                .order_by(Job.song_id, Job.created_at.desc())
            )
            result: dict[str, Job] = {}
            for job in rows:
                if job.song_id is not None:
                    result.setdefault(job.song_id, job)
            return result

    def audio_asset(self, song_id: str) -> AudioAsset | None:
        """Audio normalizzato se pronto, altrimenti l'originale."""
        with self.db.read_session() as s:
            assets = {
                a.kind: a
                for a in s.scalars(select(AudioAsset).where(AudioAsset.song_id == song_id))
            }
        return assets.get(AssetKind.NORMALIZED) or assets.get(AssetKind.ORIGINAL)

    def find_by_checksum(self, checksum: str) -> Song | None:
        with self.db.read_session() as s:
            return s.scalars(
                select(Song)
                .join(AudioAsset, AudioAsset.song_id == Song.id)
                .where(
                    AudioAsset.checksum_sha256 == checksum,
                    AudioAsset.kind == AssetKind.ORIGINAL,
                )
                .limit(1)
            ).first()

    def find_by_source_url(self, url: str) -> Song | None:
        with self.db.read_session() as s:
            return s.scalars(select(Song).where(Song.source_url == url).limit(1)).first()

    # ---------------------------------------------------------- creazione

    def create_from_upload(
        self,
        uploads: UploadService,
        pending: PendingUpload,
        title: str,
        artist: str | None,
        album: str | None,
    ) -> tuple[Song, str]:
        existing = self.find_by_checksum(pending.checksum_sha256)
        if existing is not None:
            raise _duplicate(existing)

        song_id = new_id()
        source = self.storage.upload_dir(pending.upload_id) / pending.stored_name
        dest_dir = self.storage.song_audio_dir(song_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / ("original" + pending.extension)
        shutil.move(str(source), dest)
        job_id = new_id()
        probe_audio = pending.probe.get("audio") or {}
        try:
            with self.db.session() as s:
                song = Song(
                    id=song_id,
                    title=title,
                    artist=artist,
                    album=album,
                    duration_s=pending.probe.get("duration_s"),
                    status=SongStatus.IMPORTING,
                    source_type=SourceType.FILE,
                )
                s.add(song)
                s.add(
                    AudioAsset(
                        song_id=song_id,
                        kind=AssetKind.ORIGINAL,
                        path=self.storage.to_relative(dest),
                        format=pending.extension.lstrip("."),
                        duration_s=pending.probe.get("duration_s"),
                        sample_rate=probe_audio.get("sample_rate"),
                        channels=probe_audio.get("channels"),
                        size_bytes=pending.size_bytes,
                        checksum_sha256=pending.checksum_sha256,
                    )
                )
                s.add(
                    Job(
                        id=job_id,
                        kind=IMPORT_FILE,
                        song_id=song_id,
                        payload={},
                        checkpoint={},
                        message="In coda",
                    )
                )
        except BaseException:
            remove_tree(dest_dir)
            raise
        uploads.discard(pending.upload_id)
        log.info("brano creato da file", extra={"song_id": song_id, "job_id": job_id})
        return song, job_id

    def create_from_url(
        self,
        url: str,
        title: str,
        artist: str | None,
        album: str | None,
        duration_s: float | None,
    ) -> tuple[Song, str]:
        existing = self.find_by_source_url(url)
        if existing is not None:
            raise _duplicate(existing)
        song_id = new_id()
        job_id = new_id()
        with self.db.session() as s:
            song = Song(
                id=song_id,
                title=title,
                artist=artist,
                album=album,
                duration_s=duration_s,
                status=SongStatus.IMPORTING,
                source_type=SourceType.YOUTUBE,
                source_url=url,
            )
            s.add(song)
            s.add(
                Job(
                    id=job_id,
                    kind=IMPORT_URL,
                    song_id=song_id,
                    payload={"url": url},
                    checkpoint={},
                    message="In coda",
                )
            )
        log.info("brano creato da URL", extra={"song_id": song_id, "job_id": job_id})
        return song, job_id

    # ------------------------------------------------------- modifiche

    def update_metadata(
        self, song_id: str, title: str, artist: str | None, album: str | None
    ) -> Song:
        with self.db.session() as s:
            song = s.get(Song, song_id)
            if song is None:
                raise AppError("song_not_found", "Brano non trovato.")
            song.title, song.artist, song.album = title, artist, album
            return song

    def retry(self, song_id: str) -> str:
        """Rimette in coda un brano fallito o annullato: l'analisi se l'audio è già
        importato, altrimenti l'importazione."""
        song = self.get(song_id)
        if song.status not in (SongStatus.FAILED, SongStatus.CANCELLED):
            raise AppError(
                "song_not_retryable",
                "Si può riprovare solo un'elaborazione fallita o annullata.",
                {"status": song.status.value},
            )
        self._ensure_idle(song_id)
        normalized = self.audio_asset(song_id)
        last = self.latest_jobs([song_id]).get(song_id)
        if (
            normalized is not None
            and normalized.kind is AssetKind.NORMALIZED
            and last is not None
            and last.kind == SEPARATE
        ):
            kind, payload, status = SEPARATE, dict(last.payload), SongStatus.PROCESSING
        elif normalized is not None and normalized.kind is AssetKind.NORMALIZED:
            kind, payload, status = ANALYZE, {}, SongStatus.PROCESSING
        elif song.source_type is SourceType.YOUTUBE:
            kind, payload, status = IMPORT_URL, {"url": song.source_url}, SongStatus.IMPORTING
        else:
            kind, payload, status = IMPORT_FILE, {}, SongStatus.IMPORTING
        job_id = self.queue.enqueue(kind, payload, song_id=song_id)
        with self.db.session() as s:
            current = s.get(Song, song_id)
            if current is not None:
                current.status = status
        return job_id

    def analyze(self, song_id: str) -> str:
        """Rilancia l'analisi (sostituisce i risultati precedenti)."""
        self.get(song_id)
        normalized = self.audio_asset(song_id)
        if normalized is None or normalized.kind is not AssetKind.NORMALIZED:
            raise AppError("audio_not_found", "Il brano non ha ancora un audio importato.")
        self._ensure_idle(song_id)
        job_id = self.queue.enqueue(ANALYZE, {}, song_id=song_id)
        with self.db.session() as s:
            current = s.get(Song, song_id)
            if current is not None:
                current.status = SongStatus.PROCESSING
        return job_id

    def separate(self, song_id: str, payload: dict[str, object]) -> str:
        """Accoda la separazione in stem (poi la nuova analisi)."""
        self.get(song_id)
        normalized = self.audio_asset(song_id)
        if normalized is None or normalized.kind is not AssetKind.NORMALIZED:
            raise AppError("audio_not_found", "Il brano non ha ancora un audio importato.")
        self._ensure_idle(song_id)
        job_id = self.queue.enqueue(SEPARATE, dict(payload), song_id=song_id)
        with self.db.session() as s:
            current = s.get(Song, song_id)
            if current is not None:
                current.status = SongStatus.PROCESSING
        return job_id

    def delete_stems(self, song_id: str) -> int:
        """Elimina gli stem (file e righe). Restituisce i byte liberati."""
        self.get(song_id)
        self._ensure_idle(song_id)
        with self.db.session() as s:
            freed = sum(
                st.size_bytes or 0 for st in s.scalars(select(Stem).where(Stem.song_id == song_id))
            )
            s.execute(delete(Stem).where(Stem.song_id == song_id))
        remove_tree(self.storage.root / "stems" / song_id)
        return int(freed)

    def delete(self, song_id: str) -> None:
        """Elimina brano, dati e file. Se un job è in esecuzione chiede di annullarlo e
        risponde ``song_busy``: il client riprova a job fermato."""
        self.get(song_id)
        self._ensure_idle(song_id)
        with self.db.session() as s:
            song = s.get(Song, song_id)
            if song is not None:
                s.delete(song)
        self.storage.delete_song_files(song_id)
        log.info("brano eliminato", extra={"song_id": song_id})

    def _ensure_idle(self, song_id: str) -> None:
        with self.db.read_session() as s:
            active = list(
                s.scalars(
                    select(Job).where(Job.song_id == song_id, Job.status.in_(ACTIVE_JOB_STATUSES))
                )
            )
        running = False
        for job in active:
            self.queue.request_cancel(job.id)
            running = running or job.status is not JobStatus.QUEUED
        if running:
            raise AppError(
                "song_busy",
                "Il brano è in elaborazione: ho chiesto l'annullamento, riprova tra qualche "
                "secondo.",
            )


def _duplicate(song: Song) -> AppError:
    return AppError(
        "duplicate_song",
        f"Questo brano è già nel catalogo: «{song.title}».",
        {"song_id": song.id},
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
