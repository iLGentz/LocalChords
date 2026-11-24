"""Export: accordi e testo (PDF, TXT, ChordPro), tab (PDF), mix audio (WAV, MP3), stem.

``POST /api/songs/{id}/export`` (endpoint del brief) genera subito i formati di testo e PDF e
restituisce il file; per l'audio accoda un job e restituisce il job, il cui file si scarica
da ``GET /api/exports/{job_id}``.
"""

from __future__ import annotations

import zipfile
from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.background import BackgroundTask

from app.api.deps import DatabaseDep, QueueDep, SongsDep, StorageDep
from app.api.schemas import JobOut
from app.db.base import new_id
from app.db.models import Job, JobStatus, Stem, StemStatus
from app.errors import AppError
from app.export.audio import EXPORT_AUDIO, export_dir
from app.export.render import sheet_pdf, tabs_pdf, to_chordpro, to_txt
from app.export.sheet import SheetMeta, build_sheet
from app.storage.files import safe_filename

router = APIRouter(tags=["export"])


class TrackMix(BaseModel):
    id: Annotated[str, Field(max_length=16)]
    volume: Annotated[float, Field(ge=0, le=2)] = 1.0
    muted: bool = False
    solo: bool = False


class ExportIn(BaseModel):
    format: Literal["pdf", "txt", "chordpro", "tabs_pdf", "wav", "mp3"]
    labels: dict[str, Annotated[str, Field(max_length=40)]] = Field(default_factory=dict)
    """Accordi come li mostra l'interfaccia (id → nome), già trasposti e semplificati."""
    key_label: Annotated[str | None, Field(max_length=16)] = None
    capo: Annotated[int, Field(ge=0, le=11)] = 0
    notes: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=5)
    tab_instrument: Literal["chitarra", "basso"] | None = None
    tab_rows: list[Annotated[str, Field(max_length=4000)]] = Field(
        default_factory=list, max_length=500
    )
    rate: Annotated[float, Field(ge=0.5, le=1.5)] = 1.0
    semitones: Annotated[int, Field(ge=-11, le=11)] = 0
    tracks: list[TrackMix] = Field(default_factory=list, max_length=8)


def _attachment(data: bytes, filename: str, media_type: str) -> Response:
    return Response(
        data,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/songs/{song_id}/export", response_model=None)
def export(
    song_id: str, body: ExportIn, songs: SongsDep, db: DatabaseDep, queue: QueueDep
) -> Response | JobOut:
    song = songs.get(song_id)
    meta = SheetMeta(
        title=song.title,
        artist=song.artist,
        album=song.album,
        key=body.key_label or song.key,
        capo=body.capo,
        bpm=song.bpm,
        notes=list(body.notes),
    )
    base = safe_filename(song.title + (f" - {song.artist}" if song.artist else ""))

    if body.format in ("wav", "mp3"):
        with db.read_session() as s:
            busy = s.scalars(
                select(Job).where(
                    Job.song_id == song_id,
                    Job.kind == EXPORT_AUDIO,
                    Job.status.in_((JobStatus.QUEUED, JobStatus.ANALYZING)),
                )
            ).first()
        if busy is not None:
            raise AppError("song_busy", "C'è già un export audio in corso per questo brano.")
        payload: dict[str, Any] = {
            "format": body.format,
            "rate": body.rate,
            "semitones": body.semitones,
            "tracks": [t.model_dump() for t in body.tracks] or [{"id": "mix", "volume": 1.0}],
            "key_label": body.key_label,
            "capo": body.capo,
        }
        job = queue.get(queue.enqueue(EXPORT_AUDIO, payload, song_id=song_id))
        assert job is not None
        return JobOut.from_job(job)

    if body.format == "tabs_pdf":
        if not body.tab_rows:
            raise AppError("export_empty", "Non ci sono tab da esportare.")
        data = tabs_pdf(meta, body.tab_instrument or "chitarra", body.tab_rows)
        return _attachment(
            data, f"{base} - tab {body.tab_instrument or 'chitarra'}.pdf", "application/pdf"
        )

    sheet = build_sheet(db, song_id, dict(body.labels), meta)
    if not sheet.blocks:
        raise AppError("export_empty", "Non ci sono accordi né testo da esportare.")
    if body.format == "txt":
        return _attachment(
            to_txt(sheet).encode("utf-8-sig"), f"{base}.txt", "text/plain; charset=utf-8"
        )
    if body.format == "chordpro":
        return _attachment(
            to_chordpro(sheet).encode("utf-8"), f"{base}.cho", "application/x-chordpro"
        )
    return _attachment(sheet_pdf(sheet), f"{base}.pdf", "application/pdf")


@router.get("/exports/{job_id}", response_class=FileResponse)
def download_export(job_id: str, queue: QueueDep, storage: StorageDep) -> FileResponse:
    job = queue.get(job_id)
    if job is None or job.kind != EXPORT_AUDIO:
        raise AppError("export_not_found", "Export non trovato.")
    if job.status is not JobStatus.READY:
        raise AppError("export_not_ready", "L'export non è ancora pronto.")
    result = (job.checkpoint or {}).get("data", {}).get("result") or {}
    path = storage.to_absolute(str(result.get("path", ""))) if result.get("path") else None
    if path is None or not path.is_file():
        raise AppError("export_not_found", "Il file esportato non è più disponibile.")
    media = "audio/mpeg" if path.suffix == ".mp3" else "audio/wav"
    return FileResponse(path, media_type=media, filename=str(result.get("filename", path.name)))


@router.get("/songs/{song_id}/stems/{stem_type}/download", response_class=FileResponse)
def download_stem(
    song_id: str, stem_type: str, songs: SongsDep, db: DatabaseDep, storage: StorageDep
) -> FileResponse:
    song = songs.get(song_id)
    with db.read_session() as s:
        row = next(
            (
                st
                for st in s.scalars(
                    select(Stem).where(Stem.song_id == song_id, Stem.status == StemStatus.READY)
                )
                if st.type.value == stem_type
            ),
            None,
        )
    path = storage.to_absolute(row.path) if row is not None and row.path else None
    if path is None or not path.is_file():
        raise AppError("stem_not_found", "Stem non disponibile.")
    return FileResponse(
        path, media_type="audio/flac", filename=safe_filename(f"{song.title} - {stem_type}.flac")
    )


@router.get("/songs/{song_id}/stems.zip", response_class=FileResponse)
def download_stems_zip(
    song_id: str, songs: SongsDep, db: DatabaseDep, storage: StorageDep
) -> FileResponse:
    song = songs.get(song_id)
    with db.read_session() as s:
        rows = list(
            s.scalars(select(Stem).where(Stem.song_id == song_id, Stem.status == StemStatus.READY))
        )
    files = [(st.type.value, storage.to_absolute(st.path)) for st in rows if st.path]
    files = [(t, p) for t, p in files if p.is_file()]
    if not files:
        raise AppError("stem_not_found", "Il brano non ha stem.")
    out_dir = export_dir(storage)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"stems-{new_id()}.zip"
    # FLAC è già compresso: ZIP senza ricompressione, scritto su disco (può pesare centinaia di MB).
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as zf:
        for stem_type, path in files:
            zf.write(path, arcname=safe_filename(f"{song.title} - {stem_type}.flac"))
    return FileResponse(
        target,
        media_type="application/zip",
        filename=safe_filename(f"{song.title} - stem.zip"),
        background=BackgroundTask(target.unlink, missing_ok=True),
    )
