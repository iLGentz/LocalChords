"""Ambiente Alembic.

Le migrazioni usano un motore dedicato senza ``foreign_keys=ON``: in modalità batch
SQLite ricrea le tabelle e con le FK attive un DROP TABLE farebbe scattare le cascate.
"""

from __future__ import annotations

from logging.config import fileConfig
from typing import Any, Literal

import sqlalchemy as sa
from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.db import models  # noqa: F401  (registra i modelli nei metadata)
from app.db.base import Base, UTCDateTime

config = context.config
target_metadata = Base.metadata

# Solo da riga di comando (alembic.ini): l'app configura il proprio logging JSON.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def _render_item(type_: str, obj: Any, autogen_context: AutogenContext) -> str | Literal[False]:
    """Le migrazioni non dipendono dai tipi personalizzati dell'app."""
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime()"
    if type_ == "type" and isinstance(obj, sa.Enum):
        return f"sa.String(length={obj.length})"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            render_item=_render_item,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
