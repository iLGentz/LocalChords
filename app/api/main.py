"""Applicazione FastAPI: router ``/api`` più il frontend compilato servito in statico."""

from __future__ import annotations

import logging
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse, HTMLResponse, Response

from app import __version__
from app.api.errors import ApiError, install_error_handlers
from app.api.routers import analysis, health, jobs, lyrics, practice, songs, system, tabs
from app.config import Settings, get_settings
from app.db.session import Database
from app.importing.service import SongService
from app.importing.uploads import UPLOAD_MAX_AGE_S, UploadService
from app.storage.files import Storage
from app.worker.queue import JobQueue

log = logging.getLogger(__name__)

# Su Windows i tipi MIME vengono dal registro e a volte `.js` risulta `text/plain`: il
# browser rifiuterebbe i moduli JavaScript (interfaccia e AudioWorklet). Li fissiamo.
for _ext, _type in (
    (".js", "text/javascript"),
    (".mjs", "text/javascript"),
    (".css", "text/css"),
    (".json", "application/json"),
    (".svg", "image/svg+xml"),
    (".wasm", "application/wasm"),
):
    mimetypes.add_type(_type, _ext)

_MISSING_FRONTEND = """<!doctype html><html lang="it"><head><meta charset="utf-8">
<title>LocalChords</title></head>
<body style="font-family:system-ui;background:#1c1a18;color:#e8e4de;padding:3rem">
<h1>Interfaccia non compilata</h1>
<p>Esegui <code>setup.ps1</code> oppure <code>npm run build</code> nella cartella
<code>frontend</code>.</p></body></html>"""


def create_app(settings: Settings | None = None, db: Database | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = db or Database(settings.database_path)

    storage = Storage(settings.data_dir)
    queue = JobQueue(db)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        removed = storage.cleanup_uploads(UPLOAD_MAX_AGE_S)
        if removed:
            log.info("anteprime di upload scadute rimosse", extra={"count": removed})
        yield

    app = FastAPI(
        title="LocalChords",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = db
    app.state.queue = queue
    app.state.storage = storage
    app.state.uploads = UploadService(settings, storage)
    app.state.songs = SongService(db, storage, queue)
    install_error_handlers(app)

    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    api.include_router(jobs.router)
    api.include_router(songs.router)
    api.include_router(analysis.router)
    api.include_router(system.router)
    api.include_router(lyrics.router)
    api.include_router(practice.router)
    api.include_router(tabs.router)

    @api.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE"])
    def _api_not_found(path: str) -> None:
        raise ApiError(404, "not_found", f"Endpoint inesistente: /api/{path}")

    app.include_router(api)
    _mount_frontend(app, settings.frontend_dist)
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve i file del build Vite; ogni altro percorso riceve ``index.html`` (SPA)."""
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def _frontend(path: str) -> Response:
        index = root / "index.html"
        if not index.is_file():
            return HTMLResponse(_MISSING_FRONTEND, status_code=503)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            headers = (
                {"Cache-Control": "public, max-age=31536000, immutable"}
                if path.startswith("assets/")
                else None
            )
            return FileResponse(candidate, headers=headers)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
