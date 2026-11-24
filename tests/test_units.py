"""Testi (LRC, allineamento, editor con annulla), tab, YouTube, validazione, storage, hardware."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.youtube import canonical_url
from app.errors import AppError
from app.hardware import GpuInfo, Profile, RuntimeInfo, build_profiles, recommend
from app.importing.validation import guess_metadata
from app.lyrics.align import AsrWord, align_lines
from app.lyrics.lrclib import parse_lrc
from app.storage.files import Storage, safe_filename
from app.tabs.basic_pitch import NoteEvent
from app.tabs.fretting import BASS_TUNING, GUITAR_TUNING, assign
from tests.conftest import upload_and_confirm
from tests.synth import write_progression

# ----------------------------------------------------------------- metadati


@pytest.mark.parametrize(
    ("filename", "tags", "expected"),
    [
        ("03 - Artista X - Titolo Y (Official Video).mp3", {}, ("Titolo Y", "Artista X")),
        ("solo titolo.flac", {}, ("solo titolo", None)),
        ("x.mp3", {"title": "T", "artist": "A", "album": "B"}, ("T", "A")),
    ],
)
def test_guess_metadata(
    filename: str, tags: dict[str, str], expected: tuple[str, str | None]
) -> None:
    g = guess_metadata(tags, filename)
    assert (g.title, g.artist) == expected


def test_safe_filename_and_storage(tmp_path: Path) -> None:
    assert safe_filename('a/b\\c:d*?"<>|.mp3') == "c_d______.mp3"
    st = Storage(tmp_path)
    with pytest.raises(ValueError):
        st.song_audio_dir("../../etc")
    with pytest.raises(ValueError):
        st.to_absolute("../fuori.txt")


# ------------------------------------------------------------------- YouTube


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "youtu.be/dQw4w9WgXcQ",
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=x",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
    ],
)
def test_canonical_url(url: str) -> None:
    assert canonical_url(url) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://vimeo.com/123",
        "https://youtube.com/watch?v=corto",
        "ftp://youtu.be/dQw4w9WgXcQ",
    ],
)
def test_invalid_url(url: str) -> None:
    with pytest.raises(AppError) as exc:
        canonical_url(url)
    assert exc.value.code == "invalid_url"


def test_youtube_disabled_by_default(client: TestClient) -> None:
    res = client.post("/api/songs/import-url/preview", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
    assert res.status_code == 403 and res.json()["code"] == "youtube_disabled"


# --------------------------------------------------------------------- testi


def test_parse_lrc() -> None:
    lines = parse_lrc("[ar:x]\n[00:12.50]Seconda\n[00:01.00][00:30.00]Ritornello\n\n")
    assert [(ln.start_s, ln.text) for ln in lines] == [
        (1.0, "Ritornello"),
        (12.5, "Seconda"),
        (30.0, "Ritornello"),
    ]


def test_align_matches_and_interpolates() -> None:
    asr = [
        AsrWord("ciao", 1.0, 1.3, 0.9),
        AsrWord("mondo", 1.4, 1.8, 0.9),
        AsrWord("bel", 5.0, 5.3, 0.8),
    ]
    out = align_lines([("Ciao, mondo bello!", 1.0), ("bel giorno", 4.9)], asr, 20.0)
    w = out[0].words
    assert (w[0].start_s, w[1].start_s) == (1.0, 1.4)
    assert w[2].start_s is not None and w[2].end_s is not None and w[2].end_s - w[2].start_s <= 0.6
    assert out[1].words[0].start_s == 5.0
    starts = [x.start_s for ln in out for x in ln.words if x.start_s is not None]
    assert starts == sorted(starts)


def test_lyrics_editor_with_undo(
    client: TestClient, run_worker: Callable[[], None], tmp_path: Path
) -> None:
    wav = tmp_path / "brano.wav"
    write_progression(wav, chords=["C", "G"], bpm=120.0, repeats=3)
    song_id = upload_and_confirm(client, wav)["song"]["id"]
    run_worker()
    # testo incollato in formato LRC: senza Whisper restano i tempi per riga
    lrc = "[00:01.00]Prima riga di prova\n[00:05.00]Seconda riga"
    assert (
        client.post(
            f"/api/songs/{song_id}/lyrics/refresh", json={"text": lrc, "search": False}
        ).status_code
        == 202
    )
    run_worker()
    lyrics = client.get(f"/api/songs/{song_id}/lyrics").json()
    assert lyrics["status"] == "line_synced" and lyrics["source"] == "user"
    first = lyrics["lines"][0]
    assert first["text"] == "Prima riga di prova" and len(first["words"]) == 4
    assert all(w["start_s"] is not None for w in first["words"])

    # modifica del testo con lo stesso numero di parole: i tempi restano
    before = [w["start_s"] for w in first["words"]]
    client.patch(f"/api/songs/{song_id}/lyrics/{first['id']}", json={"text": "Prima riga di test"})
    line = client.get(f"/api/songs/{song_id}/lyrics").json()["lines"][0]
    assert [w["start_s"] for w in line["words"]] == before and line["edited"]
    # spostare l'inizio sposta le parole
    client.patch(f"/api/songs/{song_id}/lyrics/{first['id']}", json={"start_s": 2.0})
    line = client.get(f"/api/songs/{song_id}/lyrics").json()["lines"][0]
    assert line["words"][0]["start_s"] == pytest.approx(before[0] + 1.0)
    # tempi non validi
    bad = client.patch(
        f"/api/songs/{song_id}/lyrics/{first['id']}", json={"start_s": 9.0, "end_s": 3.0}
    )
    assert bad.json()["code"] == "invalid_time"
    # aggiungi parola, elimina riga, annulla tutto a ritroso
    client.post(
        f"/api/songs/{song_id}/lyrics/{first['id']}/words",
        json={"after_word_id": None, "text": "Ehi"},
    )
    assert client.get(f"/api/songs/{song_id}/lyrics").json()["lines"][0]["text"].startswith("Ehi ")
    second = client.get(f"/api/songs/{song_id}/lyrics").json()["lines"][1]
    client.delete(f"/api/songs/{song_id}/lyrics/{second['id']}")
    assert len(client.get(f"/api/songs/{song_id}/lyrics").json()["lines"]) == 1
    for _ in range(4):
        assert client.post(f"/api/songs/{song_id}/undo").status_code == 200
    restored = client.get(f"/api/songs/{song_id}/lyrics").json()
    assert [ln["text"] for ln in restored["lines"]] == ["Prima riga di prova", "Seconda riga"]
    assert client.post(f"/api/songs/{song_id}/undo").json()["code"] == "nothing_to_undo"
    # ripristina originale: elimina le aggiunte dell'utente
    client.post(
        f"/api/songs/{song_id}/lyrics/lines", json={"after_line_id": None, "text": "Aggiunta"}
    )
    client.post(f"/api/songs/{song_id}/lyrics/restore")
    texts = [ln["text"] for ln in client.get(f"/api/songs/{song_id}/lyrics").json()["lines"]]
    assert texts == ["Prima riga di prova", "Seconda riga"]


# ----------------------------------------------------------------------- tab


def _notes(pitches: list[int], step: float = 0.5) -> list[NoteEvent]:
    return [NoteEvent(i * step, i * step + 0.4, p, 0.8) for i, p in enumerate(pitches)]


def test_fretting_guitar_open_chord_and_scale() -> None:
    # accordo di Mi minore suonato insieme: 6 note su 6 corde diverse
    chord = [NoteEvent(0.0, 1.0, p, 0.9) for p in (40, 47, 52, 55, 59, 64)]
    out = assign(chord, GUITAR_TUNING)
    assert len(out) == 6 and len({n.string for n in out}) == 6
    assert all(n.fret <= 2 for n in out)
    for n in out:  # coerenza nota ↔ corda/tasto
        assert GUITAR_TUNING[6 - n.string] + n.fret == n.pitch_midi
    scale = assign(_notes([60, 62, 64, 65, 67]), GUITAR_TUNING)
    assert max(n.fret for n in scale) - min(n.fret for n in scale) <= 5  # mano ferma


def test_fretting_bass_range() -> None:
    out = assign(_notes([28, 33, 20, 100]), BASS_TUNING)  # 20 e 100 fuori estensione
    assert [n.pitch_midi for n in out] == [28, 33]
    assert all(BASS_TUNING[4 - n.string] + n.fret == n.pitch_midi for n in out)


# ------------------------------------------------------------------ hardware


def test_profiles_logic() -> None:
    rt_cpu = RuntimeInfo(torch_version="2.14.1+cpu", separator_installed=True)
    p = {x.id: x for x in build_profiles([], rt_cpu)}
    assert p[Profile.LIGHT].available and not p[Profile.MAX].available
    assert recommend(list(p.values())) is Profile.LIGHT
    gpu = [GpuInfo("NVIDIA GeForce RTX 3080 Ti", 12288, "580.00")]
    rt_cuda = RuntimeInfo(torch_version="2.14.1+cu126", torch_cuda=True, separator_installed=True)
    p = {x.id: x for x in build_profiles(gpu, rt_cuda)}
    assert p[Profile.MAX].available and recommend(list(p.values())) is Profile.MAX
    small = [GpuInfo("GTX 1650", 4096, "x")]
    assert "8 GB" in (
        next(x for x in build_profiles(small, rt_cuda) if x.id is Profile.MAX).reason or ""
    )
