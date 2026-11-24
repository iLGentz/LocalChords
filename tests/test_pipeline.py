"""Pipeline completa come la usa l'interfaccia: upload, conferma, worker, risultati, export."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.config import Settings
from tests.conftest import upload_and_confirm
from tests.synth import write_progression


@pytest.fixture
def wav(tmp_path: Path) -> Path:
    path = tmp_path / "Band di prova - Canzone sintetica.wav"
    write_progression(path, chords=["C", "G", "Am", "F"], bpm=120.0, repeats=3)
    return path


def _ready_song(client: TestClient, run_worker: Callable[[], None], wav: Path) -> str:
    started = upload_and_confirm(client, wav)
    song_id = started["song"]["id"]
    assert started["job"]["status"] == "queued"
    run_worker()
    song = client.get(f"/api/songs/{song_id}").json()
    assert song["status"] == "ready", song
    return song_id  # type: ignore[no-any-return]


def test_upload_preview_metadata(client: TestClient, wav: Path) -> None:
    res = client.post(
        "/api/songs/upload", content=wav.read_bytes(), headers={"X-Filename": wav.name}
    )
    assert res.status_code == 201
    p = res.json()
    assert (p["artist"], p["title"]) == ("Band di prova", "Canzone sintetica")  # dal nome del file
    assert p["format"] == "WAV" and p["channels"] == 2 and p["sample_rate"] == 44100
    assert 23 < p["duration_s"] < 26
    assert client.delete(f"/api/songs/upload/{p['upload_id']}").status_code == 204


def test_full_pipeline(
    client: TestClient, run_worker: Callable[[], None], wav: Path, settings: Settings
) -> None:
    song_id = _ready_song(client, run_worker, wav)

    # job eseguiti in catena: import, analisi, testi (senza LRCLIB e senza Whisper)
    kinds = {j["kind"]: j["status"] for j in client.get("/api/jobs").json()}
    assert kinds == {"import_file": "ready", "analyze": "ready", "lyrics": "ready"}

    analysis = client.get(f"/api/songs/{song_id}/analysis").json()
    assert analysis["analyzed"] and abs(analysis["bpm"] - 120) < 3
    assert analysis["key"] in ("C", "Am")
    chords = [c["chord"] for c in analysis["chords"]]
    assert {"C", "G", "Am", "F"} <= set(chords)
    assert analysis["sections"] and analysis["beats"]

    # audio normalizzato FLAC 44,1 kHz stereo e waveform
    audio = client.get(f"/api/songs/{song_id}/audio")
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/flac"
    flac = settings.data_dir / "audio" / song_id / "audio.flac"
    info = sf.info(str(flac))
    assert (info.samplerate, info.channels) == (44100, 2)
    assert client.get(f"/api/songs/{song_id}/waveform").json()["peaks"]

    # testi: senza modello Whisper e senza LRCLIB lo stato lo dice chiaramente
    lyrics = client.get(f"/api/songs/{song_id}/lyrics").json()
    assert lyrics["status"] == "model_missing" and lyrics["lines"] == []
    assert lyrics["whisper"]["installed"] is False

    # catalogo e ricerca
    assert [s["id"] for s in client.get("/api/songs", params={"q": "sintetica"}).json()] == [
        song_id
    ]
    assert client.get("/api/songs", params={"q": "inesistente"}).json() == []


def test_duplicate_detected(client: TestClient, run_worker: Callable[[], None], wav: Path) -> None:
    song_id = _ready_song(client, run_worker, wav)
    res = client.post(
        "/api/songs/upload", content=wav.read_bytes(), headers={"X-Filename": wav.name}
    )
    preview = res.json()
    assert preview["duplicate_of"]["id"] == song_id
    res = client.post(f"/api/songs/upload/{preview['upload_id']}/confirm", json={"title": "copia"})
    assert res.status_code == 409 and res.json()["code"] == "duplicate_song"


def test_invalid_uploads(client: TestClient, tmp_path: Path, settings: Settings) -> None:
    def post(name: str, data: bytes) -> dict:  # type: ignore[type-arg]
        res = client.post("/api/songs/upload", content=data, headers={"X-Filename": name})
        return {"status": res.status_code, **res.json()}

    assert post("brano.exe", b"x")["code"] == "unsupported_format"
    assert post("vuoto.mp3", b"")["code"] == "empty_file"
    assert post("rotto.mp3", b"non sono un mp3" * 100)["code"] == "invalid_audio"
    short = tmp_path / "corto.wav"
    sf.write(str(short), np.zeros((44100, 2), dtype=np.float32), 44100)
    assert post("corto.wav", short.read_bytes())["code"] == "audio_too_short"
    fake = post("finto.mp3", b"RIFF" + b"\x00" * 64)  # estensione e contenuto non corrispondono
    assert fake["status"] in (415, 422)


def test_silent_audio_fails_cleanly(
    client: TestClient, run_worker: Callable[[], None], tmp_path: Path
) -> None:
    silent = tmp_path / "silenzio.wav"
    sf.write(str(silent), np.zeros((44100 * 6, 2), dtype=np.float32), 44100)
    started = upload_and_confirm(client, silent)
    run_worker()
    song = client.get(f"/api/songs/{started['song']['id']}").json()
    assert song["status"] == "failed"
    assert song["job"]["error"]["code"] == "audio_silent"


def test_cancel_and_retry(client: TestClient, run_worker: Callable[[], None], wav: Path) -> None:
    started = upload_and_confirm(client, wav)
    song_id = started["song"]["id"]
    res = client.post(f"/api/jobs/{started['job']['id']}/cancel")
    assert res.json()["status"] == "cancelled"
    assert client.get(f"/api/songs/{song_id}").json()["status"] == "cancelled"
    assert client.post(f"/api/songs/{song_id}/retry").status_code == 200
    run_worker()
    assert client.get(f"/api/songs/{song_id}").json()["status"] == "ready"


def test_practice_view_and_chord_edit_with_undo(
    client: TestClient, run_worker: Callable[[], None], wav: Path
) -> None:
    song_id = _ready_song(client, run_worker, wav)
    view = client.patch(
        f"/api/songs/{song_id}/view", json={"transpose": 2, "capo": 3, "simplification": "easy"}
    ).json()
    assert (view["transpose"], view["capo"], view["simplification"]) == (2, 3, "easy")
    assert client.patch(f"/api/songs/{song_id}/view", json={"transpose": 12}).status_code == 422

    chord = client.get(f"/api/songs/{song_id}/chords").json()[0]
    assert (
        client.patch(
            f"/api/songs/{song_id}/chords/{chord['id']}", json={"chord": "Dm7"}
        ).status_code
        == 204
    )
    assert (
        client.patch(f"/api/songs/{song_id}/chords/{chord['id']}", json={"chord": "boh"}).json()[
            "code"
        ]
        == "invalid_chord"
    )
    edited = client.get(f"/api/songs/{song_id}/chords").json()[0]
    assert (edited["chord"], edited["original_chord"]) == ("Dm7", chord["chord"])

    assert client.post(f"/api/songs/{song_id}/undo").status_code == 200
    assert client.get(f"/api/songs/{song_id}/chords").json()[0]["chord"] == chord["chord"]
    assert client.post(f"/api/songs/{song_id}/redo").status_code == 200
    assert client.get(f"/api/songs/{song_id}/chords").json()[0]["chord"] == "Dm7"
    client.post(f"/api/songs/{song_id}/chords/{chord['id']}/restore")
    assert client.get(f"/api/songs/{song_id}/chords").json()[0]["chord"] == chord["chord"]

    client.patch(f"/api/songs/{song_id}/chords/{chord['id']}", json={"simplify_exempt": True})
    assert client.get(f"/api/songs/{song_id}/chords").json()[0]["simplify_exempt"] is True

    prefs = client.put(
        "/api/settings/display",
        json={"notation": "italian", "instrument": "ukulele", "compact": True},
    )
    assert client.get("/api/settings/display").json() == prefs.json()


def test_text_and_pdf_exports(
    client: TestClient, run_worker: Callable[[], None], wav: Path
) -> None:
    song_id = _ready_song(client, run_worker, wav)
    chords = client.get(f"/api/songs/{song_id}/chords").json()
    labels = {c["id"]: c["chord"] + "*" for c in chords}  # nomi "trasformati" dal frontend
    body = {"labels": labels, "key_label": "D", "capo": 2, "notes": ["Trasposto di +2"]}

    txt = client.post(f"/api/songs/{song_id}/export", json={**body, "format": "txt"})
    assert txt.status_code == 200 and "attachment" in txt.headers["content-disposition"]
    text = txt.content.decode("utf-8-sig")
    assert (
        "Canzone sintetica - Band di prova" in text and "Tonalità: D" in text and "Capo: 2" in text
    )
    assert "C*" in text  # i nomi arrivano dal frontend, non ricalcolati

    cho = client.post(f"/api/songs/{song_id}/export", json={**body, "format": "chordpro"}).text
    assert "{title: Canzone sintetica}" in cho and "{capo: 2}" in cho and "[C*]" in cho

    pdf = client.post(f"/api/songs/{song_id}/export", json={**body, "format": "pdf"})
    assert pdf.content.startswith(b"%PDF") and pdf.headers["content-type"] == "application/pdf"

    tabs = client.post(
        f"/api/songs/{song_id}/export",
        json={
            "format": "tabs_pdf",
            "tab_instrument": "chitarra",
            "tab_rows": ["e|--0--|\nB|--1--|"],
        },
    )
    assert tabs.content.startswith(b"%PDF")


@pytest.mark.parametrize("fmt", ["wav", "mp3"])
def test_audio_export_with_speed_and_pitch(
    client: TestClient, run_worker: Callable[[], None], wav: Path, fmt: str, tmp_path: Path
) -> None:
    song_id = _ready_song(client, run_worker, wav)
    job = client.post(
        f"/api/songs/{song_id}/export",
        json={
            "format": fmt,
            "rate": 1.25,
            "semitones": -2,
            "tracks": [{"id": "mix", "volume": 1.4}],
        },
    ).json()
    assert job["status"] == "queued"
    run_worker()
    res = client.get(f"/api/exports/{job['id']}")
    assert res.status_code == 200, res.text
    out = tmp_path / f"mix.{fmt}"
    out.write_bytes(res.content)
    if fmt == "wav":
        data, sr = sf.read(str(out))
        assert sr == 44100
        original = sf.info(str(wav)).duration
        assert abs(len(data) / sr - original / 1.25) < 0.5  # 1,25x più veloce
        assert np.max(np.abs(data)) <= 0.98  # nessun clipping nonostante il volume 140%
    else:
        assert res.content[:3] == b"ID3"
        assert "1.25x" in res.headers["content-disposition"]


def test_delete_song_removes_files(
    client: TestClient, run_worker: Callable[[], None], wav: Path, settings: Settings
) -> None:
    song_id = _ready_song(client, run_worker, wav)
    assert (settings.data_dir / "audio" / song_id).is_dir()
    storage = client.get("/api/system/storage").json()
    assert storage["categories"]["audio"] > 0 and storage["songs"][0]["song_id"] == song_id
    assert client.delete(f"/api/songs/{song_id}").status_code == 204
    assert not (settings.data_dir / "audio" / song_id).exists()
    assert client.get(f"/api/songs/{song_id}").status_code == 404


def test_hardware_and_settings(client: TestClient) -> None:
    hw = client.get("/api/system/hardware").json()
    profiles = {p["id"]: p for p in hw["info"]["profiles"]}
    assert profiles["light"]["available"] is True  # runtime CPU installato
    assert profiles["balanced"]["available"] is False
    if not hw["info"]["gpus"]:
        assert profiles["max"]["available"] is False and hw["info"]["recommended"] == "light"
    prefs = client.put(
        "/api/settings/processing",
        json={"device": "cpu", "profile": "light", "auto_separate": False},
    ).json()
    assert client.get("/api/settings/processing").json() == prefs
    models = {m["id"]: m for m in client.get("/api/models").json()}
    assert {"htdemucs_6s", "bs_roformer_sw", "whisper_small"} <= set(models)
    assert models["bs_roformer_sw"]["commercial_use"] is False
