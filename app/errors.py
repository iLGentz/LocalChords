"""Errore applicativo previsto: codice stabile più messaggio comprensibile per l'utente.

Viene tradotto in errore API (``{code, message, detail}``) o in errore del job.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(self, code: str, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail
