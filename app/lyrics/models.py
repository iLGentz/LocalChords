"""Modelli Whisper (faster-whisper, licenza MIT) per profilo, scaricati su richiesta."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.hardware import Device, Profile


@dataclass(frozen=True)
class WhisperSpec:
    id: str
    label: str
    alias: str
    """Nome del modello per faster-whisper (scarica dal repository Hugging Face ufficiale)."""
    size_mb: int
    profiles: tuple[Profile, ...]
    description: str


WHISPER_MODELS: dict[str, WhisperSpec] = {
    "whisper_small": WhisperSpec(
        "whisper_small",
        "Whisper small",
        "small",
        464,
        (Profile.LIGHT,),
        "Trascrizione e allineamento dei testi su CPU (int8).",
    ),
    "whisper_medium": WhisperSpec(
        "whisper_medium",
        "Whisper medium",
        "medium",
        1460,
        (Profile.BALANCED,),
        "Più preciso di small, più lento su CPU.",
    ),
    "whisper_large_v3_turbo": WhisperSpec(
        "whisper_large_v3_turbo",
        "Whisper large-v3-turbo",
        "large-v3-turbo",
        1547,
        (Profile.MAX,),
        "Il più preciso; pensato per GPU NVIDIA.",
    ),
}

WHISPER_LICENSE = "MIT"


def whisper_dir(data_dir: Path, spec: WhisperSpec) -> Path:
    return data_dir / "models" / "whisper" / spec.id


def whisper_installed(spec: WhisperSpec, data_dir: Path) -> bool:
    d = whisper_dir(data_dir, spec)
    return (d / "model.bin").is_file() and (d / "config.json").is_file()


def whisper_size_on_disk(spec: WhisperSpec, data_dir: Path) -> int:
    d = whisper_dir(data_dir, spec)
    return sum(p.stat().st_size for p in d.rglob("*") if p.is_file()) if d.is_dir() else 0


def whisper_for_profile(profile: Profile) -> WhisperSpec:
    for spec in WHISPER_MODELS.values():
        if profile in spec.profiles:
            return spec
    return WHISPER_MODELS["whisper_small"]


def compute_type(device: Device) -> str:
    return "float16" if device is Device.CUDA else "int8"


# Secondi di calcolo per secondo di audio, finché non ci sono misure reali.
DEFAULT_RATIOS: dict[tuple[str, Device], float] = {
    ("whisper_small", Device.CPU): 0.35,
    ("whisper_small", Device.CUDA): 0.03,
    ("whisper_medium", Device.CPU): 1.0,
    ("whisper_medium", Device.CUDA): 0.06,
    ("whisper_large_v3_turbo", Device.CPU): 1.2,
    ("whisper_large_v3_turbo", Device.CUDA): 0.05,
}
