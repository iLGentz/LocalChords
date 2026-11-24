from __future__ import annotations

import shutil
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config import Settings
from app.db.migrate import upgrade_to_head
from app.db.session import Database
from app.worker.queue import JobQueue
from app.worker.registry import default_registry
from app.worker.worker import JobWorker

# Cartella dati persistente per i test lenti: i modelli scaricati restano tra un'esecuzione e
# l'altra, database e audio vengono azzerati ogni volta. Esclusa da git.
SLOW_DATA = Path(__file__).parent / ".slowdata"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: test lenti (modelli, separazione, trascrizione)")
    config.addinivalue_line("markers", "network: richiedono la rete (download di modelli o file)")


def _make_settings(data_dir: Path, logs_dir: Path, dist: Path) -> Settings:
    s = Settings(
        _env_file=None,
        data_dir=data_dir,
        logs_dir=logs_dir,
        frontend_dist=dist,
        lrclib_enabled=False,
        youtube_enabled=False,
        worker_poll_interval_s=0.05,
        worker_heartbeat_interval_s=0.2,
        worker_stale_after_s=5.0,
    )
    s.ensure_dirs()
    return s


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return _make_settings(tmp_path / "data", tmp_path / "logs", tmp_path / "dist")


@pytest.fixture
def slow_settings(tmp_path: Path) -> Settings:
    for sub in ("audio", "stems", "waveforms", "exports", "uploads", "cache"):
        shutil.rmtree(SLOW_DATA / sub, ignore_errors=True)
    for f in SLOW_DATA.glob("localchords.db*"):
        f.unlink()
    return _make_settings(SLOW_DATA, tmp_path / "logs", tmp_path / "dist")


def _db(s: Settings) -> Iterator[Database]:
    upgrade_to_head(s.database_url)
    database = Database(s.database_path)
    yield database
    database.dispose()


@pytest.fixture
def db(settings: Settings) -> Iterator[Database]:
    yield from _db(settings)


@pytest.fixture
def slow_db(slow_settings: Settings) -> Iterator[Database]:
    yield from _db(slow_settings)


@pytest.fixture
def queue(db: Database) -> JobQueue:
    return JobQueue(db)


def _client(s: Settings, d: Database) -> Iterator[TestClient]:
    with TestClient(create_app(s, d), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def client(settings: Settings, db: Database) -> Iterator[TestClient]:
    yield from _client(settings, db)


@pytest.fixture
def slow_client(slow_settings: Settings, slow_db: Database) -> Iterator[TestClient]:
    yield from _client(slow_settings, slow_db)


def _runner(s: Settings, d: Database) -> Callable[[], None]:
    def run() -> None:
        """Esegue tutti i job in coda, compresi quelli accodati a catena."""
        JobWorker(s, d, default_registry(s, d)).run(until_idle=True)

    return run


@pytest.fixture
def run_worker(settings: Settings, db: Database) -> Callable[[], None]:
    return _runner(settings, db)


@pytest.fixture
def slow_run_worker(slow_settings: Settings, slow_db: Database) -> Callable[[], None]:
    return _runner(slow_settings, slow_db)


def upload_and_confirm(client: TestClient, path: Path, title: str | None = None) -> dict:  # type: ignore[type-arg]
    """Carica un file come fa l'interfaccia e conferma l'importazione."""
    res = client.post(
        "/api/songs/upload",
        content=path.read_bytes(),
        headers={"X-Filename": path.name, "Content-Type": "application/octet-stream"},
    )
    assert res.status_code == 201, res.text
    preview = res.json()
    res = client.post(
        f"/api/songs/upload/{preview['upload_id']}/confirm",
        json={"title": title or preview["title"], "artist": preview["artist"]},
    )
    assert res.status_code == 201, res.text
    return res.json()  # type: ignore[no-any-return]
