"""Configurazione dell'app, letta da variabili d'ambiente e dal file `.env`.

Tutte le variabili hanno il prefisso ``LOCALCHORDS_`` e sono documentate in `.env.example`.
I percorsi relativi sono risolti rispetto alla cartella dell'app (la radice del repository).
"""

from __future__ import annotations

import shutil
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_ROOT = Path(__file__).resolve().parent.parent


class DevicePreference(StrEnum):
    AUTO = "auto"
    NVIDIA = "nvidia"
    CPU = "cpu"


class InstalledRuntime(StrEnum):
    """Runtime di inferenza installato da setup.ps1 (scritto in `.env`)."""

    CPU = "cpu"
    NVIDIA = "nvidia"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LOCALCHORDS_",
        env_file=APP_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    data_dir: Path = Field(default=Path("data"))
    logs_dir: Path = Field(default=Path("logs"))
    frontend_dist: Path = Field(default=Path("frontend/dist"))
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=0, le=65535)
    log_level: LogLevel = LogLevel.INFO

    installed_runtime: InstalledRuntime = InstalledRuntime.CPU
    device: DevicePreference = DevicePreference.AUTO
    cpu_threads: int = Field(default=0, ge=0, description="0 = automatico")

    max_upload_mb: int = Field(default=500, ge=1)
    youtube_enabled: bool = False
    lrclib_enabled: bool = True

    ffmpeg_path: Path | None = None

    worker_poll_interval_s: float = Field(default=1.0, gt=0)
    worker_heartbeat_interval_s: float = Field(default=5.0, gt=0)
    worker_stale_after_s: float = Field(default=30.0, gt=0)
    job_max_attempts: int = Field(default=3, ge=1)

    @field_validator("data_dir", "logs_dir", "frontend_dist", mode="after")
    @classmethod
    def _resolve_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else (APP_ROOT / value).resolve()

    @property
    def database_path(self) -> Path:
        return self.data_dir / "localchords.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"

    def resolve_ffmpeg(self) -> Path | None:
        """Trova FFmpeg: variabile esplicita, poi copia portabile in `tools/`, poi PATH."""
        if self.ffmpeg_path is not None:
            return self.ffmpeg_path if self.ffmpeg_path.is_file() else None
        bundled = APP_ROOT / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
        if bundled.is_file():
            return bundled
        found = shutil.which("ffmpeg")
        return Path(found) if found else None

    def ensure_dirs(self) -> None:
        for sub in ("audio", "stems", "waveforms", "cache", "models", "exports"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
