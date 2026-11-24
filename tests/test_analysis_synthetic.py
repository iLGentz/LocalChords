"""Analisi su audio sintetico con risultato noto (progressione C-G-Am-F a 120 BPM)."""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from app.analysis.beats import detect_beats
from app.analysis.features import Features, load_mono
from app.analysis.harmony import detect_chords, detect_key
from app.analysis.sections import detect_sections
from app.analysis.waveform import compute_peaks
from tests.synth import write_progression

CHORDS = ["C", "G", "Am", "F"]


@pytest.fixture(scope="module")
def song(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Features, list[tuple[float, float, str]], Path]:
    path = tmp_path_factory.mktemp("synth") / "prog.wav"
    truth = write_progression(path, chords=CHORDS, bpm=120.0, repeats=4)
    return Features(load_mono([path])), truth, path


def test_bpm_close_to_truth(song: tuple[Features, list, Path]) -> None:  # type: ignore[type-arg]
    f, _truth, _p = song
    grid = detect_beats(f)
    assert grid.bpm is not None
    # tollerati anche gli errori d'ottava (60/240), comuni ai beat tracker
    assert min(abs(grid.bpm - 120), abs(grid.bpm - 60), abs(grid.bpm - 240)) < 3, grid.bpm
    assert abs(grid.bpm - 120) < 3, f"BPM rilevato {grid.bpm}"
    assert grid.bpm_confidence > 0.5
    assert sum(grid.downbeats) >= 12  # 16 battute nel brano


def test_downbeats_on_bar_starts(song: tuple[Features, list, Path]) -> None:  # type: ignore[type-arg]
    f, truth, _p = song
    grid = detect_beats(f)
    bar_starts = [s for s, _e, _c in truth]
    downs = [t for t, d in zip(grid.times, grid.downbeats, strict=True) if d]
    hits = sum(1 for d in downs if min(abs(d - b) for b in bar_starts) < 0.12)
    assert hits / len(downs) >= 0.8, f"downbeat corretti {hits}/{len(downs)}"


def test_chords_accuracy(song: tuple[Features, list, Path]) -> None:  # type: ignore[type-arg]
    f, truth, _p = song
    grid = detect_beats(f)
    events = detect_chords(f, grid)
    # accuratezza pesata per durata, campionando ogni 0,1 s
    total = correct = 0
    for start, end, name in truth:
        t = start + 0.25
        while t < end - 0.25:
            total += 1
            label = next((e.chord for e in events if e.start_s <= t < e.end_s), "N")
            correct += label.split("/")[0] == name
            t += 0.1
    accuracy = correct / total
    print(f"accuratezza accordi su audio sintetico: {accuracy:.0%}")
    assert accuracy >= 0.85


def test_key(song: tuple[Features, list, Path]) -> None:  # type: ignore[type-arg]
    f, _t, _p = song
    events = detect_chords(f, detect_beats(f))
    key = detect_key(f, events)
    assert key.key in ("C", "Am"), key  # progressione I-V-vi-IV: Do maggiore (o relativa)
    assert key.confidence > 0


def test_sections_cover_song(song: tuple[Features, list, Path]) -> None:  # type: ignore[type-arg]
    f, _t, _p = song
    sections = detect_sections(f, detect_beats(f))
    assert sections and sections[0].start_s == 0.0
    assert abs(sections[-1].end_s - f.duration_s) < 0.5
    for a, b in itertools.pairwise(sections):
        assert abs(a.end_s - b.start_s) < 1e-6  # contigue, senza buchi


def test_waveform_peaks(song: tuple[Features, list, Path], tmp_path: Path) -> None:  # type: ignore[type-arg]
    f, _t, path = song
    info = compute_peaks(path, tmp_path / "peaks.json")
    assert abs(float(info["duration_s"]) - f.duration_s) < 0.1
    assert int(info["count"]) > 40 * f.duration_s
