"""Test con i modelli veri, eseguibili su CPU. Scaricano i modelli la prima volta.

Esecuzione: ``python -m pytest -m slow``. I modelli restano in ``tests/.slowdata/models``.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from tests.conftest import upload_and_confirm
from tests.synth import speech_wav, write_progression

pytestmark = [pytest.mark.slow, pytest.mark.network]


def _download(client: TestClient, run: Callable[[], None], model_id: str) -> None:
    models = {m["id"]: m for m in client.get("/api/models").json()}
    if models[model_id]["installed"]:
        return
    job = client.post(f"/api/models/{model_id}/download").json()
    run()
    done = client.get(f"/api/jobs/{job['id']}").json()
    assert done["status"] == "ready", done
    assert {m["id"]: m for m in client.get("/api/models").json()}[model_id]["installed"]


def test_separation_reanalysis_and_tabs(
    slow_client: TestClient,
    slow_run_worker: Callable[[], None],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client, run = slow_client, slow_run_worker
    wav = tmp_path / "Prova - Separazione.wav"
    write_progression(wav, chords=["C", "G", "Am", "F"], bpm=120.0, repeats=2)  # 16 s
    song_id = upload_and_confirm(client, wav)["song"]["id"]
    run()

    _download(client, run, "htdemucs_6s")
    plan = client.get(f"/api/songs/{song_id}/separation-plan", params={"device": "cpu"}).json()
    assert plan["model_id"] == "htdemucs_6s" and plan["device"] == "cpu" and plan["model_installed"]

    t0 = time.monotonic()
    job = client.post(f"/api/songs/{song_id}/separate", json={"device": "cpu"}).json()
    run()  # separazione, poi nuova analisi e testi in catena
    elapsed = time.monotonic() - t0
    sep = client.get(f"/api/jobs/{job['id']}").json()
    assert sep["status"] == "ready", sep

    stems = {s["type"]: s for s in client.get(f"/api/songs/{song_id}/stems").json()}
    assert set(stems) == {"vocals", "drums", "bass", "guitar", "piano", "other"}
    with capsys.disabled():
        print(f"\n  separazione di 16 s su CPU (con rianalisi): {elapsed:.1f} s")

    # gli stem sono file FLAC validi della stessa durata; il basso contiene energia,
    # la voce quasi nulla (il brano sintetico non ha voce)
    rms = {}
    for t, s in stems.items():
        res = client.get(s["url"])
        assert res.status_code == 200
        p = tmp_path / f"{t}.flac"
        p.write_bytes(res.content)
        data, sr = sf.read(str(p))
        assert sr == 44100 and abs(len(data) / sr - 17) < 1.5
        rms[t] = float(np.sqrt(np.mean(np.square(data))))
    with capsys.disabled():
        print("  energia RMS per stem:", {k: round(v, 4) for k, v in rms.items()})
    assert rms["bass"] > 5 * rms["vocals"]

    # la nuova analisi ha usato gli stem (mix senza voce e batteria) e trova ancora gli accordi
    analysis = client.get(f"/api/songs/{song_id}/analysis").json()
    assert {"C", "G", "Am", "F"} <= {c["chord"] for c in analysis["chords"]}
    jobs = [
        j
        for j in client.get("/api/jobs").json()
        if j["song_id"] == song_id and j["kind"] == "analyze"
    ]
    assert len(jobs) == 2 and all(j["status"] == "ready" for j in jobs)

    # tab dagli stem: il basso suona le fondamentali C, G, A, F
    tab_job = client.post(f"/api/songs/{song_id}/tabs").json()
    run()
    assert client.get(f"/api/jobs/{tab_job['id']}").json()["status"] == "ready"
    tabs = client.get(f"/api/songs/{song_id}/tabs").json()
    assert tabs["bass"] is not None and tabs["bass"]["notes"]
    pcs = Counter(n["pitch_midi"] % 12 for n in tabs["bass"]["notes"])
    top = {pc for pc, _ in pcs.most_common(4)}
    with capsys.disabled():
        print("  classi di altezza del basso più frequenti:", pcs.most_common(6))
    assert top <= {0, 7, 9, 5, 4, 2, 11}  # note della scala di Do; le fondamentali in testa
    assert len(top & {0, 7, 9, 5}) >= 3

    # gli stem si eliminano e lo spazio torna libero
    assert client.delete(f"/api/songs/{song_id}/stems").json()["freed_bytes"] > 0
    assert client.get(f"/api/songs/{song_id}/stems").json() == []


TEXT = "Questa è una prova della sintesi vocale. Le parole devono essere allineate al tempo giusto."


def test_whisper_transcription_and_alignment(
    slow_client: TestClient,
    slow_run_worker: Callable[[], None],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client, run = slow_client, slow_run_worker
    voice = tmp_path / "Voce - Prova.wav"
    if not speech_wav(voice, TEXT):
        pytest.skip("Sintesi vocale di Windows non disponibile")
    song_id = upload_and_confirm(client, voice)["song"]["id"]
    run()
    assert client.get(f"/api/songs/{song_id}").json()["status"] == "ready"

    _download(client, run, "whisper_small")

    # 1) trascrizione senza testo di riferimento
    t0 = time.monotonic()
    client.post(f"/api/songs/{song_id}/lyrics/refresh", json={"search": False})
    run()
    lyrics = client.get(f"/api/songs/{song_id}/lyrics").json()
    with capsys.disabled():
        print(f"\n  trascrizione Whisper small su CPU: {time.monotonic() - t0:.1f} s")
        print("  testo trascritto:", " / ".join(ln["text"] for ln in lyrics["lines"]))
    assert lyrics["status"] == "transcribed" and lyrics["source"] == "transcription"
    words = " ".join(ln["text"] for ln in lyrics["lines"]).lower()
    expected = {"prova", "sintesi", "vocale", "parole", "tempo"}
    found = {w for w in expected if w in words}
    assert len(found) >= 3, found

    # 2) testo incollato allineato parola per parola alla voce
    client.post(f"/api/songs/{song_id}/lyrics/refresh", json={"text": TEXT, "search": False})
    run()
    lyrics = client.get(f"/api/songs/{song_id}/lyrics").json()
    assert lyrics["status"] == "aligned" and lyrics["source"] == "user"
    timed = [w for ln in lyrics["lines"] for w in ln["words"]]
    assert len(timed) == len(TEXT.split())
    starts = [w["start_s"] for w in timed]
    assert all(s is not None for s in starts) and starts == sorted(starts)
    duration = sf.info(str(voice)).duration
    assert 0 <= starts[0] < 1.5 and starts[-1] < duration
    matched = sum(1 for w in timed if (w["confidence"] or 0) > 0.3)
    with capsys.disabled():
        print(f"  parole allineate con buona confidenza: {matched}/{len(timed)}")
    assert matched / len(timed) >= 0.6
