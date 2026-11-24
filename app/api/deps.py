"""Dipendenze FastAPI: configurazione, database e coda presi dallo stato dell'app."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.db.session import Database
from app.importing.service import SongService
from app.importing.uploads import UploadService
from app.storage.files import Storage
from app.worker.queue import JobQueue


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_db(request: Request) -> Database:
    db: Database = request.app.state.db
    return db


def get_queue(request: Request) -> JobQueue:
    queue: JobQueue = request.app.state.queue
    return queue


def get_songs(request: Request) -> SongService:
    songs: SongService = request.app.state.songs
    return songs


def get_uploads(request: Request) -> UploadService:
    uploads: UploadService = request.app.state.uploads
    return uploads


def get_storage(request: Request) -> Storage:
    storage: Storage = request.app.state.storage
    return storage


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DatabaseDep = Annotated[Database, Depends(get_db)]
QueueDep = Annotated[JobQueue, Depends(get_queue)]
SongsDep = Annotated[SongService, Depends(get_songs)]
UploadsDep = Annotated[UploadService, Depends(get_uploads)]
StorageDep = Annotated[Storage, Depends(get_storage)]
