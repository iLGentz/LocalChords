"""Assegnazione di corda e tasto alle note (programmazione dinamica).

Le note che iniziano quasi insieme (entro 40 ms) formano un gruppo da suonare su corde
diverse. Per ogni gruppo si generano le diteggiature possibili; il costo premia:
- mano ferma (spostamento della posizione media dei tasti tra gruppi),
- tasti bassi e corde a vuoto,
- accordi compatti (estensione tra tasti ≤ 4).
Viterbi sulla sequenza dei gruppi sceglie la diteggiatura complessiva più comoda.
Il risultato è "indicativo": il timbro della chitarra non dice su quale corda è suonata
una nota.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from app.tabs.basic_pitch import NoteEvent

# Accordature standard, dalla corda più grave (indice 0) alla più acuta (MIDI).
GUITAR_TUNING = (40, 45, 50, 55, 59, 64)  # E2 A2 D3 G3 B3 E4
BASS_TUNING = (28, 33, 38, 43)  # E1 A1 D2 G2
MAX_FRET = 20
GROUP_WINDOW_S = 0.04
MAX_CANDIDATES = 40


@dataclass(frozen=True)
class FrettedNote:
    start_s: float
    duration_s: float
    pitch_midi: int
    string: int
    """1 = corda più acuta (convenzione delle tab)."""
    fret: int
    velocity: float


def playable_range(tuning: tuple[int, ...]) -> tuple[int, int]:
    return tuning[0], tuning[-1] + MAX_FRET


def _positions(pitch: int, tuning: tuple[int, ...]) -> list[tuple[int, int]]:
    return [(s, pitch - open_) for s, open_ in enumerate(tuning) if 0 <= pitch - open_ <= MAX_FRET]


def _group(notes: list[NoteEvent], n_strings: int) -> list[list[NoteEvent]]:
    groups: list[list[NoteEvent]] = []
    for note in sorted(notes, key=lambda n: (n.start_s, n.pitch_midi)):
        if (
            groups
            and note.start_s - groups[-1][0].start_s <= GROUP_WINDOW_S
            and len(groups[-1]) < n_strings
        ):
            if all(n.pitch_midi != note.pitch_midi for n in groups[-1]):
                groups[-1].append(note)
            continue
        groups.append([note])
    return groups


def _candidates(
    group: list[NoteEvent], tuning: tuple[int, ...]
) -> list[tuple[tuple[int, int], ...]]:
    options = [_positions(n.pitch_midi, tuning) for n in group]
    if any(not o for o in options):
        return []
    result: list[tuple[tuple[int, int], ...]] = []
    for combo in itertools.product(*options):
        strings = [s for s, _f in combo]
        if len(set(strings)) != len(strings):
            continue
        frets = [f for _s, f in combo if f > 0]
        if frets and max(frets) - min(frets) > 4:
            continue
        result.append(combo)
        if len(result) >= MAX_CANDIDATES:
            break
    return result


def _position(combo: tuple[tuple[int, int], ...]) -> float:
    frets = [f for _s, f in combo if f > 0]
    return sum(frets) / len(frets) if frets else 0.0


def _static_cost(combo: tuple[tuple[int, int], ...]) -> float:
    frets = [f for _s, f in combo]
    fretted = [f for f in frets if f > 0]
    span = (max(fretted) - min(fretted)) if fretted else 0
    return 0.08 * sum(frets) / len(frets) + 0.3 * span + (0 if fretted else -0.2)


def assign(notes: list[NoteEvent], tuning: tuple[int, ...]) -> list[FrettedNote]:
    low, high = playable_range(tuning)
    notes = [n for n in notes if low <= n.pitch_midi <= high]
    groups = _group(notes, len(tuning))
    groups_with_options = [(g, _candidates(g, tuning)) for g in groups]
    # Gruppi impossibili (corde insufficienti): si tiene la nota più grave e si riprova.
    fixed: list[tuple[list[NoteEvent], list[tuple[tuple[int, int], ...]]]] = []
    for g, opts in groups_with_options:
        while not opts and len(g) > 1:
            g = sorted(g, key=lambda n: n.pitch_midi)[:-1]
            opts = _candidates(g, tuning)
        if opts:
            fixed.append((g, opts))
    if not fixed:
        return []

    # Viterbi
    costs = [_static_cost(c) for c in fixed[0][1]]
    back: list[list[int]] = []
    for idx in range(1, len(fixed)):
        prev_opts = fixed[idx - 1][1]
        cur_opts = fixed[idx][1]
        gap = fixed[idx][0][0].start_s - fixed[idx - 1][0][0].start_s
        move_weight = 0.6 if gap < 0.5 else 0.25  # muoversi è più facile dopo una pausa
        new_costs: list[float] = []
        pointers: list[int] = []
        prev_pos = [_position(p) for p in prev_opts]
        for cur in cur_opts:
            pos = _position(cur)
            best_j, best = 0, float("inf")
            for j, pc in enumerate(costs):
                moved = abs(pos - prev_pos[j]) if pos and prev_pos[j] else 0.0
                total = pc + move_weight * moved
                if total < best:
                    best_j, best = j, total
            new_costs.append(best + _static_cost(cur))
            pointers.append(best_j)
        back.append(pointers)
        costs = new_costs

    choice = min(range(len(costs)), key=lambda i: costs[i])
    path = [choice]
    for pointers in reversed(back):
        choice = pointers[choice]
        path.append(choice)
    path.reverse()

    n_strings = len(tuning)
    out: list[FrettedNote] = []
    for (group, opts), ci in zip(fixed, path, strict=True):
        for note, (string_idx, fret) in zip(group, opts[ci], strict=True):
            out.append(
                FrettedNote(
                    start_s=note.start_s,
                    duration_s=round(max(note.end_s - note.start_s, 0.01), 4),
                    pitch_midi=note.pitch_midi,
                    string=n_strings - string_idx,
                    fret=fret,
                    velocity=note.amplitude,
                )
            )
    return out
