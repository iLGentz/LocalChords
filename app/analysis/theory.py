"""Nomi di note, accordi e tonalità usati dall'analisi.

Gli accordi si salvano con i diesis (forma canonica: ``C#m7``, ``F#/A#``); la grafia con i
bemolle, la trasposizione e le notazioni italiana e numerica si applicano in visualizzazione.
"""

from __future__ import annotations

from dataclasses import dataclass

SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
# Grafia convenzionale delle tonalità (Eb maggiore, non D# maggiore).
MAJOR_KEY_NAMES = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
MINOR_KEY_NAMES = ("Cm", "C#m", "Dm", "Ebm", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "Bbm", "Bm")

NO_CHORD = "N"


@dataclass(frozen=True)
class Quality:
    name: str
    suffix: str
    intervals: tuple[int, ...]
    weights: tuple[float, ...]
    prior: float
    """Penalità a priori: le qualità più complesse devono "meritarsi" la scelta."""


QUALITIES: tuple[Quality, ...] = (
    Quality("maj", "", (0, 4, 7), (1.0, 0.9, 0.8), 0.0),
    Quality("min", "m", (0, 3, 7), (1.0, 0.9, 0.8), 0.0),
    Quality("7", "7", (0, 4, 7, 10), (1.0, 0.9, 0.7, 0.6), 0.035),
    Quality("maj7", "maj7", (0, 4, 7, 11), (1.0, 0.9, 0.7, 0.6), 0.04),
    Quality("m7", "m7", (0, 3, 7, 10), (1.0, 0.9, 0.7, 0.6), 0.035),
    Quality("sus4", "sus4", (0, 5, 7), (1.0, 0.9, 0.8), 0.05),
    Quality("sus2", "sus2", (0, 2, 7), (1.0, 0.9, 0.8), 0.06),
    Quality("dim", "dim", (0, 3, 6), (1.0, 0.9, 0.8), 0.06),
    Quality("aug", "aug", (0, 4, 8), (1.0, 0.9, 0.8), 0.07),
)

# Accordi diatonici per grado (scala maggiore): qualità triade ammessa su ciascun grado.
_MAJOR_DIATONIC = {0: "maj", 2: "min", 4: "min", 5: "maj", 7: "maj", 9: "min", 11: "dim"}


def chord_name(root: int, quality: Quality, bass: int | None = None) -> str:
    name = SHARP_NAMES[root % 12] + quality.suffix
    if bass is not None and bass % 12 != root % 12:
        name += "/" + SHARP_NAMES[bass % 12]
    return name


def key_name(tonic: int, minor: bool) -> str:
    return (MINOR_KEY_NAMES if minor else MAJOR_KEY_NAMES)[tonic % 12]


def is_diatonic(root: int, quality: Quality, tonic: int, minor: bool) -> bool:
    """Vero se la triade dell'accordo appartiene alla tonalità (minore = relativa maggiore)."""
    major_tonic = (tonic + 3) % 12 if minor else tonic
    degree = (root - major_tonic) % 12
    expected = _MAJOR_DIATONIC.get(degree)
    if expected is None:
        return False
    base = {"maj": "maj", "7": "maj", "maj7": "maj", "min": "min", "m7": "min"}.get(quality.name)
    if base is None:
        return (quality.name == "dim" and expected == "dim") or quality.name.startswith("sus")
    # Il V7 in minore (dominante armonica) è comune: lo consideriamo coerente.
    if minor and degree == 4 and quality.name in ("maj", "7"):
        return True
    return base == expected
