"""Preferenze dell'utente salvate in SQLite (tabella ``user_preferences``)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from app.config import DevicePreference, Settings
from app.db.base import utcnow
from app.db.models import UserPreference
from app.db.session import Database

ProfileChoice = Literal["auto", "light", "balanced", "max"]


class ProcessingPreferences(BaseModel):
    device: DevicePreference = DevicePreference.AUTO
    profile: ProfileChoice = "auto"
    auto_separate: bool = True


_KEYS = tuple(ProcessingPreferences.model_fields)


def load(db: Database, settings: Settings) -> ProcessingPreferences:
    with db.read_session() as s:
        rows = {
            r.key: r.value
            for r in s.scalars(select(UserPreference).where(UserPreference.key.in_(_KEYS)))
        }
    data = {"device": settings.device, **rows}
    try:
        return ProcessingPreferences.model_validate(data)
    except ValidationError:
        return ProcessingPreferences(device=settings.device)


def save(db: Database, prefs: ProcessingPreferences) -> ProcessingPreferences:
    with db.session() as s:
        for key, value in prefs.model_dump(mode="json").items():
            row = s.get(UserPreference, key)
            if row is None:
                s.add(UserPreference(key=key, value=value))
            else:
                row.value = value
                row.updated_at = utcnow()
    return prefs
