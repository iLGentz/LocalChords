"""Motore SQLite condiviso da API e worker (processi diversi, stesso file).

- WAL: letture e scritture concorrenti tra processi.
- ``busy_timeout``: attende invece di fallire subito se il file è bloccato.
- ``foreign_keys``: SQLite le ignora se non attivate esplicitamente.
- Transazioni gestite da SQLAlchemy (non dal modulo sqlite3), come raccomandato
  dalla documentazione di SQLAlchemy per pysqlite.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def _on_connect(dbapi_connection: Any, _record: Any) -> None:
    dbapi_connection.isolation_level = None
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.close()


def _on_begin(conn: Any) -> None:
    mode = conn.get_execution_options().get("sqlite_begin", "DEFERRED")
    conn.exec_driver_sql(f"BEGIN {mode}")


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.url = f"sqlite:///{path.as_posix()}"
        self.engine: Engine = create_engine(
            self.url, connect_args={"check_same_thread": False, "timeout": 10}
        )
        event.listen(self.engine, "connect", _on_connect)
        event.listen(self.engine, "begin", _on_begin)
        self._write = sessionmaker(
            self.engine.execution_options(sqlite_begin="IMMEDIATE"), expire_on_commit=False
        )
        self._read = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Sessione di scrittura: commit all'uscita, rollback in caso di errore.

        Usa ``BEGIN IMMEDIATE``: il lock di scrittura si prende subito (attendendo con
        ``busy_timeout``). Con ``BEGIN`` semplice una transazione che prima legge e poi
        scrive fallirebbe con "database is locked" se un altro processo ha scritto nel
        frattempo, senza attendere.
        """
        with self._write() as session, session.begin():
            yield session

    @contextmanager
    def read_session(self) -> Iterator[Session]:
        """Sessione di sola lettura: non blocca gli altri processi."""
        with self._read() as session, session.begin():
            yield session

    def dispose(self) -> None:
        self.engine.dispose()
