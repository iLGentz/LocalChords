"""Catalogo dei modelli di separazione e loro stato su disco.

I file stanno in ``data/models/separation/``. I modelli si scaricano solo su richiesta,
mostrando prima la dimensione; si possono eliminare dalle impostazioni.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.hardware import Device, Profile


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    filename: str
    """Nome con cui audio-separator carica il modello."""
    files: tuple[str, ...]
    """File che devono esistere nella cartella dei modelli perché sia installato."""
    size_mb: int
    license: str
    commercial_use: bool
    profiles: tuple[Profile, ...]
    description: str


MODELS: dict[str, ModelSpec] = {
    "htdemucs_6s": ModelSpec(
        id="htdemucs_6s",
        label="HT-Demucs 6 stem",
        filename="htdemucs_6s.yaml",
        files=("htdemucs_6s.yaml", "5c90dfd2-34c22ccb.th"),
        size_mb=53,
        license="MIT",
        commercial_use=True,
        profiles=(Profile.LIGHT,),
        description="Leggero, adatto alla CPU. Chitarra e piano meno precisi.",
    ),
    "bs_roformer_sw": ModelSpec(
        id="bs_roformer_sw",
        label="BS-RoFormer SW",
        filename="BS-Roformer-SW.ckpt",
        files=("BS-Roformer-SW.ckpt", "BS-Roformer-SW.yaml"),
        size_mb=668,
        license="CC-BY-NC-SA-4.0",
        commercial_use=False,
        profiles=(Profile.BALANCED, Profile.MAX),
        description="Qualità massima, pensato per GPU NVIDIA. Solo uso non commerciale.",
    ),
}

# Secondi di calcolo per secondo di audio, usati finché non ci sono misure reali.
DEFAULT_RATIOS: dict[tuple[str, Device], float] = {
    ("htdemucs_6s", Device.CPU): 1.0,
    ("htdemucs_6s", Device.CUDA): 0.05,
    ("bs_roformer_sw", Device.CPU): 6.0,
    ("bs_roformer_sw", Device.CUDA): 0.15,
}


def models_dir(data_dir: Path) -> Path:
    return data_dir / "models" / "separation"


def is_installed(spec: ModelSpec, data_dir: Path) -> bool:
    directory = models_dir(data_dir)
    return all((directory / f).is_file() for f in spec.files)


def size_on_disk(spec: ModelSpec, data_dir: Path) -> int:
    directory = models_dir(data_dir)
    return sum((directory / f).stat().st_size for f in spec.files if (directory / f).is_file())


def model_for_profile(profile: Profile) -> ModelSpec:
    return MODELS["bs_roformer_sw" if profile is not Profile.LIGHT else "htdemucs_6s"]
