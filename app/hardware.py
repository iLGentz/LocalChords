"""Rilevamento dell'hardware, profili di elaborazione e stima dei tempi.

- GPU NVIDIA: ``nvidia-smi`` (nome, VRAM, driver).
- Runtime: torch (e se vede CUDA) e provider di ONNX Runtime, verificati in un processo
  separato per non caricare torch nel processo dell'API.
- RAM e CPU: API di Windows.

Profili (vedi PIANO.md):
    light     htdemucs_6s su CPU                     sempre disponibile
    balanced  BS-RoFormer SW su DirectML             non ancora supportato (vedi DECISIONI)
    max       BS-RoFormer SW su CUDA                 NVIDIA con almeno 8 GB e torch CUDA
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

log = logging.getLogger(__name__)

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
CACHE_TTL_S = 600.0
MAX_PROFILE_MIN_VRAM_MB = 8 * 1024


class Profile(StrEnum):
    LIGHT = "light"
    BALANCED = "balanced"
    MAX = "max"


class Device(StrEnum):
    CPU = "cpu"
    CUDA = "cuda"


@dataclass(frozen=True)
class GpuInfo:
    name: str
    vram_mb: int | None
    driver: str | None


@dataclass(frozen=True)
class RuntimeInfo:
    torch_version: str | None = None
    torch_cuda: bool = False
    torch_cuda_device: str | None = None
    onnx_providers: list[str] = field(default_factory=list)
    separator_installed: bool = False
    error: str | None = None


@dataclass(frozen=True)
class ProfileInfo:
    id: Profile
    label: str
    separation_model: str
    device: Device
    whisper: str
    sections: str
    available: bool
    reason: str | None


@dataclass(frozen=True)
class HardwareInfo:
    cpu: str
    cpu_cores: int
    ram_gb: float | None
    gpus: list[GpuInfo]
    runtime: RuntimeInfo
    profiles: list[ProfileInfo]
    recommended: Profile

    @property
    def cuda_ready(self) -> bool:
        return self.runtime.torch_cuda

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------- rilevamento


def detect_gpus() -> list[GpuInfo]:
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return []
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_NO_WINDOW,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    gpus: list[GpuInfo] = []
    for line in out.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3:
            vram = int(parts[1]) if parts[1].isdigit() else None
            gpus.append(GpuInfo(parts[0], vram, parts[2] or None))
    return gpus


def ram_gb() -> float | None:
    if sys.platform != "win32":
        return None

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    total = int(status.ullTotalPhys)
    return round(total / 1024**3, 1)


def probe_runtime() -> RuntimeInfo:
    """Interroga torch e ONNX Runtime in un sottoprocesso (``python -m app.hardware``)."""
    try:
        out = subprocess.run(
            [sys.executable, "-m", "app.hardware"],
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=_NO_WINDOW,
            check=False,
        )
        data = json.loads(out.stdout.strip().splitlines()[-1])
        return RuntimeInfo(**data)
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError, TypeError) as exc:
        log.warning("verifica dei runtime non riuscita", extra={"error": str(exc)})
        return RuntimeInfo(error="Verifica dei runtime non riuscita")


def _probe_in_process() -> dict[str, Any]:
    info: dict[str, Any] = {"onnx_providers": []}
    try:
        import torch

        info["torch_version"] = str(torch.__version__)
        info["torch_cuda"] = bool(torch.cuda.is_available())
        if info["torch_cuda"]:
            info["torch_cuda_device"] = str(torch.cuda.get_device_name(0))
    except Exception:
        info["torch_version"] = None
    try:
        import onnxruntime

        info["onnx_providers"] = list(onnxruntime.get_available_providers())
    except Exception:
        pass
    try:
        import importlib.util

        info["separator_installed"] = importlib.util.find_spec("audio_separator") is not None
    except Exception:
        info["separator_installed"] = False
    return info


# ------------------------------------------------------------------- profili


def build_profiles(gpus: list[GpuInfo], runtime: RuntimeInfo) -> list[ProfileInfo]:
    best_vram = max((g.vram_mb or 0 for g in gpus), default=0)
    no_sep = None if runtime.separator_installed else "Runtime di separazione non installato"
    max_reason: str | None
    if not gpus:
        max_reason = "Nessuna GPU NVIDIA rilevata"
    elif best_vram < MAX_PROFILE_MIN_VRAM_MB:
        max_reason = f"Servono almeno 8 GB di VRAM (rilevati {best_vram // 1024} GB)"
    elif not runtime.torch_cuda:
        max_reason = "PyTorch con CUDA non installato: riesegui setup.ps1 -Runtime nvidia"
    else:
        max_reason = no_sep
    return [
        ProfileInfo(
            Profile.LIGHT,
            "Leggero",
            "htdemucs_6s",
            Device.CPU,
            "small int8",
            "librosa",
            no_sep is None,
            no_sep,
        ),
        ProfileInfo(
            Profile.BALANCED,
            "Bilanciato",
            "bs_roformer_sw",
            Device.CPU,
            "medium",
            "librosa",
            False,
            "DirectML non ancora supportato in questa versione",
        ),
        ProfileInfo(
            Profile.MAX,
            "Massima qualità",
            "bs_roformer_sw",
            Device.CUDA,
            "large-v3-turbo",
            "SongFormer",
            max_reason is None,
            max_reason,
        ),
    ]


def recommend(profiles: list[ProfileInfo]) -> Profile:
    available = {p.id for p in profiles if p.available}
    return Profile.MAX if Profile.MAX in available else Profile.LIGHT


_cache: tuple[float, HardwareInfo] | None = None
_lock = threading.Lock()


def detect(refresh: bool = False) -> HardwareInfo:
    """Informazioni sull'hardware, in cache per 10 minuti."""
    global _cache
    with _lock:
        if _cache is not None and not refresh and time.monotonic() - _cache[0] < CACHE_TTL_S:
            return _cache[1]
        gpus = detect_gpus()
        runtime = probe_runtime()
        profiles = build_profiles(gpus, runtime)
        info = HardwareInfo(
            cpu=platform.processor() or platform.machine(),
            cpu_cores=os.cpu_count() or 1,
            ram_gb=ram_gb(),
            gpus=gpus,
            runtime=runtime,
            profiles=profiles,
            recommended=recommend(profiles),
        )
        _cache = (time.monotonic(), info)
        log.info(
            "hardware rilevato",
            extra={"gpus": [g.name for g in gpus], "cuda": runtime.torch_cuda},
        )
        return info


if __name__ == "__main__":
    print(json.dumps(_probe_in_process()))
