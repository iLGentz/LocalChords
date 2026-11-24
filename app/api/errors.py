"""Errori API strutturati: ``{"code", "message", "detail"}``, mai stack trace al client."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import AppError

log = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: Any = None


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail


def not_found(what: str, ident: str) -> ApiError:
    return ApiError(404, f"{what}_not_found", f"Elemento non trovato: {what} {ident}")


def _response(status: int, code: str, message: str, detail: Any = None) -> JSONResponse:
    body = ErrorBody(code=code, message=message, detail=detail)
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


_HTTP_CODES = {
    400: ("bad_request", "Richiesta non valida"),
    404: ("not_found", "Risorsa non trovata"),
    405: ("method_not_allowed", "Metodo non consentito"),
    413: ("payload_too_large", "Contenuto troppo grande"),
}


# Stato HTTP per i codici degli errori applicativi (AppError). Predefinito: 400.
APP_ERROR_STATUS: dict[str, int] = {
    "file_too_large": 413,
    "unsupported_format": 415,
    "empty_file": 422,
    "invalid_audio": 422,
    "no_audio_track": 422,
    "audio_too_short": 422,
    "audio_too_long": 422,
    "audio_silent": 422,
    "invalid_url": 422,
    "live_not_supported": 422,
    "upload_not_found": 404,
    "song_not_found": 404,
    "audio_not_found": 404,
    "waveform_not_found": 404,
    "stem_not_found": 404,
    "chord_not_found": 404,
    "invalid_chord": 422,
    "stems_missing": 409,
    "lyric_line_not_found": 404,
    "lyric_word_not_found": 404,
    "invalid_time": 422,
    "empty_text": 422,
    "invalid_word": 422,
    "nothing_to_undo": 409,
    "nothing_to_redo": 409,
    "model_not_found": 404,
    "model_busy": 409,
    "model_missing": 409,
    "gpu_unavailable": 409,
    "separation_unavailable": 409,
    "separation_runtime_missing": 501,
    "video_unavailable": 404,
    "duplicate_song": 409,
    "song_busy": 409,
    "song_not_retryable": 409,
    "youtube_disabled": 403,
    "video_private": 403,
    "video_age_restricted": 403,
    "video_geo_blocked": 403,
    "youtube_not_installed": 501,
    "youtube_runtime_missing": 501,
    "network_error": 502,
    "download_failed": 502,
    "ffmpeg_missing": 503,
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_req: Request, exc: ApiError) -> JSONResponse:
        return _response(exc.status_code, exc.code, exc.message, exc.detail)

    @app.exception_handler(AppError)
    async def _app_error(_req: Request, exc: AppError) -> JSONResponse:
        status = APP_ERROR_STATUS.get(exc.code, 400)
        return _response(status, exc.code, exc.message, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation(_req: Request, exc: RequestValidationError) -> JSONResponse:
        detail = [
            {"loc": list(err.get("loc", [])), "msg": err.get("msg"), "type": err.get("type")}
            for err in exc.errors()
        ]
        return _response(422, "validation_error", "Dati della richiesta non validi", detail)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_req: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, message = _HTTP_CODES.get(exc.status_code, ("http_error", "Errore HTTP"))
        return _response(exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def _unexpected(req: Request, exc: Exception) -> JSONResponse:
        log.exception("errore inatteso nell'API", extra={"path": req.url.path})
        return _response(
            500,
            "internal_error",
            "Errore interno. I dettagli sono stati registrati in logs/app.log.",
        )
