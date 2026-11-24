"""Catalogo e importazione dei brani.

Import da file in due passi:
    POST /api/songs/upload                      corpo = byte del file, header X-Filename
                                                → anteprima dei metadati (nessun brano creato)
    POST /api/songs/upload/{upload_id}/confirm  → crea il brano e accoda l'importazione
    DELETE /api/songs/upload/{upload_id}        → scarta l'anteprima

Import da YouTube (se attivato):
    POST /api/songs/import-url/preview          → anteprima dei metadati del video
    POST /api/songs/import-url                  → crea il brano e accoda il download
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import unquote

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app.adapters.youtube import YouTubeAdapter, canonical_url
from app.api.deps import SettingsDep, SongsDep, StorageDep, UploadsDep
from app.api.schemas import (
    ImportStartedOut,
    ImportUrlIn,
    JobOut,
    SongMetadataIn,
    SongOut,
    SongRef,
    UploadPreviewOut,
    UrlIn,
    UrlPreviewOut,
)
from app.db.models import Song
from app.errors import AppError
from app.importing.service import SongService
from app.worker.queue import JobQueue

router = APIRouter(prefix="/songs", tags=["songs"])

_AUDIO_TYPES = {
    "flac": "audio/flac",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "webm": "audio/webm",
    "opus": "audio/ogg",
}


def _ref(song: Song | None) -> SongRef | None:
    return None if song is None else SongRef(id=song.id, title=song.title, artist=song.artist)


def _song_out(songs: SongService, song: Song) -> SongOut:
    job = songs.latest_jobs([song.id]).get(song.id)
    return SongOut.from_song(song, job, has_audio=songs.audio_asset(song.id) is not None)


def _started(songs: SongService, queue: JobQueue, song: Song, job_id: str) -> ImportStartedOut:
    job = queue.get(job_id)
    assert job is not None
    return ImportStartedOut(song=_song_out(songs, song), job=JobOut.from_job(job))


# ----------------------------------------------------------------- catalogo


@router.get("", response_model=list[SongOut])
def list_songs(
    songs: SongsDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[SongOut]:
    items = songs.list_songs(q, limit)
    ids = [s.id for s in items]
    jobs = songs.latest_jobs(ids)
    # L'interfaccia apre i brani dai dati del catalogo: senza audio_url non avrebbe il player.
    audio = songs.with_audio(ids)
    return [SongOut.from_song(s, jobs.get(s.id), has_audio=s.id in audio) for s in items]


# --------------------------------------------------------------- upload file


@router.post("/upload", response_model=UploadPreviewOut, status_code=201)
async def upload(
    request: Request,
    uploads: UploadsDep,
    songs: SongsDep,
    x_filename: Annotated[str, Header(alias="X-Filename", max_length=1000)],
) -> UploadPreviewOut:
    length_header = request.headers.get("content-length")
    length = int(length_header) if length_header and length_header.isdigit() else None
    pending = await uploads.receive(request.stream(), unquote(x_filename), length)
    duplicate = await run_in_threadpool(songs.find_by_checksum, pending.checksum_sha256)
    audio = pending.probe.get("audio") or {}
    return UploadPreviewOut(
        upload_id=pending.upload_id,
        filename=pending.filename,
        size_bytes=pending.size_bytes,
        format=pending.extension.lstrip(".").upper(),
        codec=audio.get("codec"),
        duration_s=pending.probe.get("duration_s"),
        sample_rate=audio.get("sample_rate"),
        channels=audio.get("channels"),
        title=pending.title,
        artist=pending.artist,
        album=pending.album,
        duplicate_of=_ref(duplicate),
    )


@router.post("/upload/{upload_id}/confirm", response_model=ImportStartedOut, status_code=201)
def confirm_upload(
    upload_id: str, body: SongMetadataIn, request: Request, uploads: UploadsDep, songs: SongsDep
) -> ImportStartedOut:
    pending = uploads.get(upload_id)
    song, job_id = songs.create_from_upload(uploads, pending, body.title, body.artist, body.album)
    return _started(songs, request.app.state.queue, song, job_id)


@router.delete("/upload/{upload_id}", status_code=204)
def discard_upload(upload_id: str, uploads: UploadsDep) -> Response:
    uploads.discard(upload_id)
    return Response(status_code=204)


# ------------------------------------------------------------------ YouTube


@router.post("/import-url/preview", response_model=UrlPreviewOut)
def preview_url(body: UrlIn, settings: SettingsDep, songs: SongsDep) -> UrlPreviewOut:
    adapter = YouTubeAdapter(settings)
    url = canonical_url(body.url)
    duplicate = songs.find_by_source_url(url)
    info = adapter.preview(url)
    return UrlPreviewOut(
        url=info.url,
        title=info.title,
        artist=info.artist,
        album=info.album,
        duration_s=info.duration_s,
        duplicate_of=_ref(duplicate),
    )


@router.post("/import-url", response_model=ImportStartedOut, status_code=201)
def import_url(
    body: ImportUrlIn, request: Request, settings: SettingsDep, songs: SongsDep
) -> ImportStartedOut:
    YouTubeAdapter(settings)  # verifica che l'adapter sia attivo e installato
    url = canonical_url(body.url)
    song, job_id = songs.create_from_url(url, body.title, body.artist, body.album, None)
    return _started(songs, request.app.state.queue, song, job_id)


# -------------------------------------------------------------- singolo brano


@router.get("/{song_id}", response_model=SongOut)
def get_song(song_id: str, songs: SongsDep) -> SongOut:
    return _song_out(songs, songs.get(song_id))


@router.patch("/{song_id}", response_model=SongOut)
def update_song(song_id: str, body: SongMetadataIn, songs: SongsDep) -> SongOut:
    song = songs.update_metadata(song_id, body.title, body.artist, body.album)
    return _song_out(songs, song)


@router.delete("/{song_id}", status_code=204)
def delete_song(song_id: str, songs: SongsDep) -> Response:
    songs.delete(song_id)
    return Response(status_code=204)


@router.post("/{song_id}/retry", response_model=ImportStartedOut)
def retry_song(song_id: str, request: Request, songs: SongsDep) -> ImportStartedOut:
    job_id = songs.retry(song_id)
    return _started(songs, request.app.state.queue, songs.get(song_id), job_id)


@router.get("/{song_id}/audio", response_class=FileResponse)
def song_audio(song_id: str, songs: SongsDep, storage: StorageDep) -> FileResponse:
    songs.get(song_id)
    asset = songs.audio_asset(song_id)
    path = storage.to_absolute(asset.path) if asset is not None else None
    if asset is None or path is None or not path.is_file():
        raise AppError("audio_not_found", "L'audio di questo brano non è disponibile.")
    return FileResponse(path, media_type=_AUDIO_TYPES.get(asset.format, "application/octet-stream"))
