"""Errori API strutturati: ``{"code", "message", "detail"}``, mai stack trace al client."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

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


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_req: Request, exc: ApiError) -> JSONResponse:
        return _response(exc.status_code, exc.code, exc.message, exc.detail)

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
