"""Database, migrazioni, coda dei job, worker, API di base."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import insert, inspect, select, text, update

from app.config import Settings
from app.db.base import utcnow
from app.db.migrate import alembic_config, current_revision, head_revision, upgrade_to_head
from app.db.models import Job, JobStatus, Song, SourceType, Worker
from app.db.session import Database
from app.worker.context import JobContext, JobError
from app.worker.queue import JobQueue, _hostname, pid_alive
from app.worker.registry import HandlerRegistry
from app.worker.worker import JobWorker

KINDS = {"test": JobStatus.ANALYZING}


# ------------------------------------------------------------------ database


def test_migrations_head_and_tables(db: Database) -> None:
    assert current_revision(db.engine) == head_revision()
    tables = set(inspect(db.engine).get_table_names())
    assert {
        "songs",
        "jobs",
        "chord_events",
        "lyric_words",
        "edit_history",
        "tab_notes",
        "workers",
    } <= tables
    cols = {c["name"] for c in inspect(db.engine).get_columns("chord_events")}
    assert "simplify_exempt" in cols


def test_migrations_reversible(settings: Settings, db: Database) -> None:
    command.downgrade(alembic_config(settings.database_url), "base")
    assert "songs" not in inspect(db.engine).get_table_names()
    upgrade_to_head(settings.database_url)
    assert current_revision(db.engine) == head_revision()


def test_sqlite_pragmas(db: Database) -> None:
    with db.engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_cascade_and_utc(db: Database) -> None:
    with db.session() as s:
        song = Song(title="x", source_type=SourceType.FILE)
        s.add(song)
        s.flush()
        s.add(Job(kind="k", song_id=song.id))
    with db.read_session() as s:
        assert s.scalars(select(Job)).one().created_at.tzinfo is UTC
    with db.session() as s:
        s.delete(s.scalars(select(Song)).one())
    with db.read_session() as s:
        assert s.scalars(select(Job)).all() == []


def test_naive_datetime_rejected(db: Database) -> None:
    with pytest.raises(Exception, match="fuso orario"), db.session() as s:
        s.add(Job(kind="x", created_at=datetime(2026, 1, 1)))
        s.flush()


# ---------------------------------------------------------------------- coda


def test_queue_lifecycle(queue: JobQueue) -> None:
    job_id = queue.enqueue("test", {"a": 1})
    wid = queue.register_worker()
    claimed = queue.claim(wid, KINDS)
    assert claimed is not None and claimed.id == job_id and claimed.attempts == 1
    queue.report(job_id, phase="p", progress=0.5, message="m", eta_s=3)
    job = queue.get(job_id)
    assert job is not None and (job.status, job.phase, job.progress) == (
        JobStatus.ANALYZING,
        "p",
        0.5,
    )
    queue.complete(job_id)
    job = queue.get(job_id)
    assert job is not None and job.status is JobStatus.READY and job.progress == 1.0
    assert queue.claim(wid, KINDS) is None


def test_queue_fifo_and_kinds(queue: JobQueue) -> None:
    queue.enqueue("other")
    a, b = queue.enqueue("test"), queue.enqueue("test")
    wid = queue.register_worker()
    first, second = queue.claim(wid, KINDS), queue.claim(wid, KINDS)
    assert first is not None and second is not None
    assert [first.id, second.id] == [a, b]


def test_concurrent_claims_and_writers(db: Database) -> None:
    """Più worker e un "client API" con connessioni separate: nessun duplicato, nessun lock."""
    ids = {JobQueue(db).enqueue("test") for _ in range(30)}
    taken: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()
    done = threading.Event()

    def worker() -> None:
        own = Database(db.path)
        try:
            q = JobQueue(own)
            wid = q.register_worker()
            while (job := q.claim(wid, KINDS)) is not None:
                q.report(job.id, progress=0.5)
                q.complete(job.id)
                with lock:
                    taken.append(job.id)
        except BaseException as exc:
            errors.append(exc)
        finally:
            own.dispose()

    def api_client() -> None:
        own = Database(db.path)
        try:
            while not done.is_set():
                with own.session() as s:
                    job = s.scalars(select(Job).limit(1)).first()
                    if job is not None:
                        s.execute(update(Job).where(Job.id == job.id).values(eta_s=1.0))
        except BaseException as exc:
            errors.append(exc)
        finally:
            own.dispose()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    side = threading.Thread(target=api_client)
    side.start()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    done.set()
    side.join()
    assert errors == []
    assert sorted(taken) == sorted(ids)


def test_cancel_queued_and_running(queue: JobQueue) -> None:
    queued = queue.enqueue("test")
    job = queue.request_cancel(queued)
    assert job is not None and job.status is JobStatus.CANCELLED
    running = queue.enqueue("test")
    queue.claim(queue.register_worker(), KINDS)
    job = queue.request_cancel(running)
    assert job is not None and job.cancel_requested and job.status is JobStatus.ANALYZING


def test_song_status_follows_failed_job(db: Database, queue: JobQueue) -> None:
    from app.db.models import SongStatus

    with db.session() as s:
        song = Song(title="x", source_type=SourceType.FILE, status=SongStatus.IMPORTING)
        s.add(song)
        s.flush()
        song_id = song.id
    job_id = queue.enqueue("test", song_id=song_id)
    queue.claim(queue.register_worker(), KINDS)
    queue.fail(job_id, "boom", "errore")
    with db.read_session() as s:
        assert s.get_one(Song, song_id).status is SongStatus.FAILED


def _dead_worker(db: Database, stale: bool) -> str:
    wid = "d" * 32
    beat = utcnow() - timedelta(seconds=60 if stale else 0)
    with db.session() as s:
        s.execute(
            insert(Worker).values(
                id=wid, pid=2**31 - 2, hostname=_hostname(), started_at=beat, heartbeat_at=beat
            )
        )
    return wid


def test_recovery_of_orphans(db: Database, queue: JobQueue) -> None:
    job_id = queue.enqueue("test")
    queue.claim(_dead_worker(db, stale=False), KINDS)  # processo inesistente sullo stesso PC
    report = queue.recover_stale(stale_after_s=30, max_attempts=3)
    assert report.requeued == [job_id]
    job = queue.get(job_id)
    assert job is not None and job.status is JobStatus.QUEUED


def test_recovery_gives_up_after_max_attempts(db: Database, queue: JobQueue) -> None:
    job_id = queue.enqueue("test")
    queue.claim(_dead_worker(db, stale=True), KINDS)
    with db.session() as s:
        s.execute(update(Job).where(Job.id == job_id).values(attempts=3))
    assert queue.recover_stale(stale_after_s=30, max_attempts=3).failed == [job_id]


def test_pid_alive() -> None:
    import os

    assert pid_alive(os.getpid())
    assert not pid_alive(2**31 - 2)


# -------------------------------------------------------------------- worker


def test_worker_phases_errors_and_resume(settings: Settings, db: Database) -> None:
    calls: dict[str, int] = {"a": 0, "b": 0}
    holder: dict[str, JobWorker] = {}
    first = threading.Event()

    def bump(name: str) -> str:
        calls[name] += 1
        return name.upper()

    def handler(ctx: JobContext) -> None:
        if ctx.payload.get("fail") == "expected":
            raise JobError("bad_input", "Messaggio per l'utente")
        if ctx.payload.get("fail") == "crash":
            raise RuntimeError("dettaglio interno")
        ctx.run_phase("a", lambda: bump("a"))
        if not first.is_set():
            first.set()
            holder["w"].stop_event.set()  # chiusura dell'app a metà
        ctx.run_phase("b", lambda: bump("b"))

    reg = HandlerRegistry()
    reg.register("demo", JobStatus.ANALYZING, handler)
    q = JobQueue(db)
    ok = q.enqueue("demo")
    w1 = JobWorker(settings, db, reg)
    holder["w"] = w1
    w1.run(until_idle=True)
    job = q.get(ok)
    assert (
        job is not None and job.status is JobStatus.QUEUED and job.checkpoint["completed"] == ["a"]
    )
    JobWorker(settings, db, reg).run(until_idle=True)
    job = q.get(ok)
    assert job is not None and job.status is JobStatus.READY
    assert calls == {"a": 1, "b": 1}  # la fase "a" non viene ripetuta

    expected = q.enqueue("demo", {"fail": "expected"})
    crash = q.enqueue("demo", {"fail": "crash"})
    JobWorker(settings, db, reg).run(until_idle=True)
    e, c = q.get(expected), q.get(crash)
    assert (
        e is not None
        and e.error_code == "bad_input"
        and e.error_message == "Messaggio per l'utente"
    )
    assert (
        c is not None
        and c.error_code == "internal_error"
        and "interno" not in (c.error_message or "")
    )


# ----------------------------------------------------------------------- API


def _error(body: dict[str, object], code: str) -> None:
    assert set(body) == {"code", "message", "detail"} and body["code"] == code


def test_health(client: TestClient, queue: JobQueue) -> None:
    body = client.get("/api/health").json()
    assert body["database"]["ok"] and body["status"] == "degraded"
    assert body["ffmpeg"]["available"] is True  # FFmpeg portabile in tools\ffmpeg
    queue.register_worker()
    assert client.get("/api/health").json()["status"] == "ok"


def test_structured_errors(client: TestClient) -> None:
    _error(client.get("/api/jobs/nope").json(), "job_not_found")
    _error(client.get("/api/non-esiste").json(), "not_found")
    res = client.get("/api/jobs", params={"limit": 0})
    assert res.status_code == 422
    _error(res.json(), "validation_error")
    _error(client.get("/api/songs/nope").json(), "song_not_found")


def test_spa_fallback(client: TestClient, settings: Settings) -> None:
    assert client.get("/").status_code == 503
    (settings.frontend_dist / "assets").mkdir(parents=True)
    (settings.frontend_dist / "index.html").write_text("<div id=root></div>", "utf-8")
    (settings.frontend_dist / "assets" / "a.js").write_text("x", "utf-8")
    assert client.get("/catalogo").text == "<div id=root></div>"
    res = client.get("/assets/a.js")
    assert res.headers["content-type"].startswith("text/javascript")
    assert client.get("/..%2F..%2Fpyproject.toml").text == "<div id=root></div>"


def test_openapi_has_brief_endpoints(client: TestClient) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]
    for p in (
        "/api/songs/upload",
        "/api/songs/import-url",
        "/api/songs",
        "/api/songs/{song_id}",
        "/api/jobs/{job_id}",
        "/api/jobs/{job_id}/cancel",
        "/api/songs/{song_id}/chords",
        "/api/songs/{song_id}/lyrics",
        "/api/songs/{song_id}/stems",
        "/api/songs/{song_id}/chords/{chord_id}",
        "/api/songs/{song_id}/lyrics/{line_id}",
        "/api/songs/{song_id}/export",
        "/api/health",
    ):
        assert p in paths, p


def test_hostname_utc_helper() -> None:
    assert utcnow().tzinfo is UTC
    assert _hostname()
