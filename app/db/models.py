"""Modelli del database.

Convenzioni:
- Le entità modificabili dall'utente conservano il valore dell'analisi nei campi
  ``original_*`` e quello corrente nei campi senza prefisso. ``origin`` indica se l'entità
  viene dall'analisi o è stata aggiunta dall'utente; l'eliminazione è logica
  (``is_deleted``) così da poter "ripristinare l'originale".
- I tempi sono in secondi (float) dall'inizio del brano.
- I percorsi dei file sono relativi alla cartella ``data/``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import ID, Base, UTCDateTime, new_id, str_enum, utcnow

# --------------------------------------------------------------------------- enum


class SourceType(StrEnum):
    FILE = "file"
    YOUTUBE = "youtube"


class SongStatus(StrEnum):
    IMPORTING = "importing"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    SEPARATING = "separating"
    ANALYZING = "analyzing"
    ALIGNING = "aligning"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_JOB_STATUSES

    @property
    def is_running(self) -> bool:
        return self in RUNNING_JOB_STATUSES


TERMINAL_JOB_STATUSES = frozenset({JobStatus.READY, JobStatus.FAILED, JobStatus.CANCELLED})
RUNNING_JOB_STATUSES = frozenset(
    {JobStatus.DOWNLOADING, JobStatus.SEPARATING, JobStatus.ANALYZING, JobStatus.ALIGNING}
)


class AssetKind(StrEnum):
    ORIGINAL = "original"
    NORMALIZED = "normalized"


class StemType(StrEnum):
    VOCALS = "vocals"
    DRUMS = "drums"
    BASS = "bass"
    GUITAR = "guitar"
    PIANO = "piano"
    OTHER = "other"


class StemStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class Origin(StrEnum):
    ANALYSIS = "analysis"
    USER = "user"


class LyricsSource(StrEnum):
    LRCLIB = "lrclib"
    TRANSCRIPTION = "transcription"
    USER = "user"


class Instrument(StrEnum):
    GUITAR = "guitar"
    BASS = "bass"


class Simplification(StrEnum):
    ORIGINAL = "original"
    INTERMEDIATE = "intermediate"
    EASY = "easy"


class EditAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RESTORE = "restore"


# ------------------------------------------------------------------------ mixin


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class EditableMixin:
    origin: Mapped[Origin] = mapped_column(
        str_enum(Origin), default=Origin.ANALYSIS, nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


# ----------------------------------------------------------------------- brani


class Song(TimestampMixin, Base):
    __tablename__ = "songs"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    artist: Mapped[str | None] = mapped_column(String(500))
    album: Mapped[str | None] = mapped_column(String(500))
    duration_s: Mapped[float | None] = mapped_column(Float)
    status: Mapped[SongStatus] = mapped_column(
        str_enum(SongStatus), default=SongStatus.IMPORTING, nullable=False, index=True
    )
    source_type: Mapped[SourceType] = mapped_column(str_enum(SourceType), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000))

    key: Mapped[str | None] = mapped_column(String(16))
    original_key: Mapped[str | None] = mapped_column(String(16))
    key_confidence: Mapped[float | None] = mapped_column(Float)

    bpm: Mapped[float | None] = mapped_column(Float)
    original_bpm: Mapped[float | None] = mapped_column(Float)
    bpm_confidence: Mapped[float | None] = mapped_column(Float)
    beats_per_bar: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    beat_offset_s: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    original_beat_offset_s: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Impostazioni di visualizzazione per brano, persistenti.
    transpose: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    capo: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    simplification: Mapped[Simplification] = mapped_column(
        str_enum(Simplification), default=Simplification.ORIGINAL, nullable=False
    )
    lyrics_source: Mapped[LyricsSource | None] = mapped_column(str_enum(LyricsSource))

    assets: Mapped[list[AudioAsset]] = relationship(
        back_populates="song", cascade="all, delete-orphan", passive_deletes=True
    )
    stems: Mapped[list[Stem]] = relationship(
        back_populates="song", cascade="all, delete-orphan", passive_deletes=True
    )
    jobs: Mapped[list[Job]] = relationship(
        back_populates="song", cascade="all, delete-orphan", passive_deletes=True
    )


class AudioAsset(Base):
    __tablename__ = "audio_assets"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    song_id: Mapped[str] = mapped_column(
        ID, ForeignKey("songs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[AssetKind] = mapped_column(str_enum(AssetKind), nullable=False)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_s: Mapped[float | None] = mapped_column(Float)
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    song: Mapped[Song] = relationship(back_populates="assets")


class Stem(Base):
    __tablename__ = "stems"
    __table_args__ = (UniqueConstraint("song_id", "type"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    song_id: Mapped[str] = mapped_column(
        ID, ForeignKey("songs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[StemType] = mapped_column(str_enum(StemType), nullable=False)
    path: Mapped[str | None] = mapped_column(String(1000))
    format: Mapped[str] = mapped_column(String(16), default="flac", nullable=False)
    default_volume: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    status: Mapped[StemStatus] = mapped_column(
        str_enum(StemStatus), default=StemStatus.PENDING, nullable=False
    )
    model: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    song: Mapped[Song] = relationship(back_populates="stems")


class Beat(Base):
    """Beat grid rilevata. Il tempo corrente è ``time_s + songs.beat_offset_s``."""

    __tablename__ = "beats"
    __table_args__ = (Index("ix_beats_song_time", "song_id", "time_s"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[str] = mapped_column(
        ID, ForeignKey("songs.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    time_s: Mapped[float] = mapped_column(Float, nullable=False)
    is_downbeat: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bar: Mapped[int | None] = mapped_column(Integer)


class ChordEvent(EditableMixin, TimestampMixin, Base):
    __tablename__ = "chord_events"
    __table_args__ = (Index("ix_chord_events_song_start", "song_id", "start_s"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    song_id: Mapped[str] = mapped_column(
        ID, ForeignKey("songs.id", ondelete="CASCADE"), nullable=False
    )
    start_s: Mapped[float] = mapped_column(Float, nullable=False)
    end_s: Mapped[float] = mapped_column(Float, nullable=False)
    chord: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    beat_position: Mapped[int | None] = mapped_column(Integer)
    original_start_s: Mapped[float | None] = mapped_column(Float)
    original_end_s: Mapped[float | None] = mapped_column(Float)
    original_chord: Mapped[str | None] = mapped_column(String(32))
    simplify_exempt: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    """L'utente ha ripristinato questo accordo: la semplificazione non lo tocca."""


class Section(EditableMixin, TimestampMixin, Base):
    __tablename__ = "sections"
    __table_args__ = (Index("ix_sections_song_start", "song_id", "start_s"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    song_id: Mapped[str] = mapped_column(
        ID, ForeignKey("songs.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str] = mapped_column(String(16), nullable=False)
    start_s: Mapped[float] = mapped_column(Float, nullable=False)
    end_s: Mapped[float] = mapped_column(Float, nullable=False)
    original_name: Mapped[str | None] = mapped_column(String(100))
    original_color: Mapped[str | None] = mapped_column(String(16))
    original_start_s: Mapped[float | None] = mapped_column(Float)
    original_end_s: Mapped[float | None] = mapped_column(Float)


class LyricLine(EditableMixin, TimestampMixin, Base):
    __tablename__ = "lyric_lines"
    __table_args__ = (Index("ix_lyric_lines_song_position", "song_id", "position"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    song_id: Mapped[str] = mapped_column(
        ID, ForeignKey("songs.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_s: Mapped[float | None] = mapped_column(Float)
    end_s: Mapped[float | None] = mapped_column(Float)
    original_text: Mapped[str | None] = mapped_column(Text)
    original_start_s: Mapped[float | None] = mapped_column(Float)
    original_end_s: Mapped[float | None] = mapped_column(Float)

    words: Mapped[list[LyricWord]] = relationship(
        back_populates="line",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LyricWord.position",
    )


class LyricWord(EditableMixin, TimestampMixin, Base):
    __tablename__ = "lyric_words"
    __table_args__ = (Index("ix_lyric_words_line_position", "line_id", "position"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    line_id: Mapped[str] = mapped_column(
        ID, ForeignKey("lyric_lines.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(String(200), nullable=False)
    start_s: Mapped[float | None] = mapped_column(Float)
    end_s: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    original_text: Mapped[str | None] = mapped_column(String(200))
    original_start_s: Mapped[float | None] = mapped_column(Float)
    original_end_s: Mapped[float | None] = mapped_column(Float)

    line: Mapped[LyricLine] = relationship(back_populates="words")


class TabNote(Base):
    __tablename__ = "tab_notes"
    __table_args__ = (Index("ix_tab_notes_song_instr_start", "song_id", "instrument", "start_s"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[str] = mapped_column(
        ID, ForeignKey("songs.id", ondelete="CASCADE"), nullable=False
    )
    instrument: Mapped[Instrument] = mapped_column(str_enum(Instrument), nullable=False)
    string: Mapped[int] = mapped_column(Integer, nullable=False)
    fret: Mapped[int] = mapped_column(Integer, nullable=False)
    pitch_midi: Mapped[int] = mapped_column(Integer, nullable=False)
    start_s: Mapped[float] = mapped_column(Float, nullable=False)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    velocity: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)


class EditHistory(Base):
    """Cronologia persistente delle modifiche, per annulla e ripristina.

    ``before`` e ``after`` sono istantanee JSON dei campi toccati. Le voci con ``undone``
    vero formano lo stack di "ripristina"; una nuova modifica le scarta. ``group_id``
    raggruppa più voci annullabili in un solo passo (es. dividere un accordo).
    """

    __tablename__ = "edit_history"
    __table_args__ = (Index("ix_edit_history_song_id_seq", "song_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[str] = mapped_column(
        ID, ForeignKey("songs.id", ondelete="CASCADE"), nullable=False
    )
    group_id: Mapped[str] = mapped_column(ID, nullable=False, default=new_id)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[EditAction] = mapped_column(str_enum(EditAction), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    undone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class UserPreference(Base):
    """Preferenze utente come coppie chiave/valore JSON (tema, notazione, strumento, ...)."""

    __tablename__ = "user_preferences"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


# ------------------------------------------------------------------------ job


class Job(Base):
    """Job della coda persistente.

    ``checkpoint`` contiene ``{"completed": [fasi...], "data": {...}}``: un job interrotto
    riparte saltando le fasi già completate.
    """

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_created", "status", "created_at"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    song_id: Mapped[str | None] = mapped_column(
        ID, ForeignKey("songs.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        str_enum(JobStatus), default=JobStatus.QUEUED, nullable=False
    )
    phase: Mapped[str | None] = mapped_column(String(64))
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    message: Mapped[str | None] = mapped_column(String(500))
    eta_s: Mapped[float | None] = mapped_column(Float)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(1000))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    worker_id: Mapped[str | None] = mapped_column(ID)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    song: Mapped[Song | None] = relationship(back_populates="jobs")


class Worker(Base):
    """Processi worker attivi, con heartbeat per rilevare quelli morti."""

    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    current_job_id: Mapped[str | None] = mapped_column(ID)


class TimingSample(Base):
    """Durate reali misurate per fase, usate per stimare il tempo dei job futuri."""

    __tablename__ = "timing_samples"
    __table_args__ = (Index("ix_timing_samples_phase_device", "phase", "device"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phase: Mapped[str] = mapped_column(String(64), nullable=False)
    device: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    audio_duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    elapsed_s: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
