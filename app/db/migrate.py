"""Esecuzione programmatica delle migrazioni Alembic (all'avvio e nei test)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def alembic_config(database_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def upgrade_to_head(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")


def head_revision() -> str | None:
    script = ScriptDirectory.from_config(alembic_config("sqlite://"))
    return script.get_current_head()


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def main() -> int:
    """``python -m app.db.migrate``: crea le cartelle dati e porta il database all'ultima
    versione (usato da setup.ps1)."""
    from app.config import get_settings

    settings = get_settings()
    settings.ensure_dirs()
    upgrade_to_head(settings.database_url)
    print(f"    Database aggiornato alla revisione {head_revision()}: {settings.database_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
