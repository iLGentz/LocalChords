"""Server API senza finestra, per lo sviluppo: ``uv run localchords-api [--reload]``.

In sviluppo avvia separatamente il worker (``uv run localchords-worker``) e il frontend
(``npm run dev`` in ``frontend/``).
"""

from __future__ import annotations

import argparse
import sys

import uvicorn

from app.config import get_settings
from app.db.migrate import upgrade_to_head
from app.logging_setup import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="localchords-api")
    parser.add_argument("--reload", action="store_true", help="ricarica al cambio del codice")
    args = parser.parse_args(argv)

    settings = get_settings()
    settings.ensure_dirs()
    configure_logging(settings.logs_dir, "app", settings.log_level.value)
    upgrade_to_head(settings.database_url)
    uvicorn.run(
        "app.api.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port or 8765,
        reload=args.reload,
        log_config=None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
