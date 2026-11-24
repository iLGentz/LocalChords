"""Job ``export_audio``: il mix come lo si sente nel player, in WAV o MP3.

- tracce: gli stem (o il mix completo) con volume, mute e solo del mixer;
- velocità e tonalità: Rubber Band tramite pedalboard (``time_stretch``), indipendenti;
- livello: se la somma supera -0,2 dBFS viene abbassata (niente clipping nel file);
- MP3: ffmpeg (LAME, 320 kbit/s) con titolo, artista, album e un commento con tonalità,
  capo e BPM.
Il file finisce in ``data/exports/<job_id>.<ext>`` e si scarica da ``/api/exports/{job_id}``.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import soundfile as sf
from sqlalchemy import select

from app.config import Settings
from app.db.models import AssetKind, AudioAsset, JobStatus, Song, Stem, StemStatus
from app.db.session import Database
from app.media.ffmpeg import MediaTools
from app.storage.files import Storage, safe_filename
from app.worker.context import JobContext, JobError
from app.worker.registry import HandlerRegistry

log = logging.getLogger(__name__)

EXPORT_AUDIO = "export_audio"
SAMPLE_RATE = 44100
PEAK_LIMIT = 0.977  # -0,2 dBFS
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def register(registry: HandlerRegistry, settings: Settings, db: Database) -> None:
    registry.register(EXPORT_AUDIO, JobStatus.ANALYZING, partial(run_export_audio, settings, db))


def export_dir(storage: Storage) -> Path:
    return storage.root / "exports"


def _sources(db: Database, storage: Storage, song_id: str) -> dict[str, Path]:
    with db.read_session() as s:
        stems = list(
            s.scalars(select(Stem).where(Stem.song_id == song_id, Stem.status == StemStatus.READY))
        )
        mix = s.scalars(
            select(AudioAsset).where(
                AudioAsset.song_id == song_id, AudioAsset.kind == AssetKind.NORMALIZED
            )
        ).first()
    out = {st.type.value: storage.to_absolute(st.path) for st in stems if st.path}
    if mix is not None:
        out["mix"] = storage.to_absolute(mix.path)
    return out


def _gains(tracks: list[dict[str, Any]]) -> dict[str, float]:
    any_solo = any(t.get("solo") for t in tracks)
    gains: dict[str, float] = {}
    for t in tracks:
        audible = not t.get("muted") and (not any_solo or t.get("solo"))
        gains[str(t["id"])] = float(t.get("volume", 1.0)) if audible else 0.0
    return gains


def run_export_audio(settings: Settings, db: Database, ctx: JobContext) -> None:
    song_id = ctx.song_id
    if song_id is None:
        raise JobError("invalid_job", "Export senza brano.")
    payload = ctx.payload
    fmt = str(payload.get("format", "wav"))
    rate = float(payload.get("rate", 1.0))
    semitones = float(payload.get("semitones", 0.0))
    tracks: list[dict[str, Any]] = list(payload.get("tracks") or [{"id": "mix", "volume": 1.0}])
    storage = Storage(settings.data_dir)
    sources = _sources(db, storage, song_id)
    gains = _gains(tracks)

    ctx.stage(JobStatus.ANALYZING, "mix", "Missaggio delle tracce")
    mix: npt.NDArray[np.float32] | None = None
    active = [tid for tid, g in gains.items() if g > 0]
    if not active:
        raise JobError("export_silent", "Tutte le tracce sono mute: non c'è niente da esportare.")
    for i, tid in enumerate(active):
        ctx.check()
        path = sources.get(tid)
        if path is None or not path.is_file():
            raise JobError("export_source_missing", f"Traccia non disponibile: {tid}.")
        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
        if sr != SAMPLE_RATE:
            raise JobError(
                "export_source_invalid", "Frequenza di campionamento inattesa negli stem."
            )
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        data = data[:, :2] * gains[tid]
        if mix is None:
            mix = data
        else:
            n = max(len(mix), len(data))
            mix = np.pad(mix, ((0, n - len(mix)), (0, 0))) + np.pad(
                data, ((0, n - len(data)), (0, 0))
            )
        ctx.progress(0.4 * (i + 1) / len(active))
    assert mix is not None

    if abs(rate - 1.0) > 1e-3 or abs(semitones) > 1e-3:
        ctx.stage(JobStatus.ANALYZING, "stretch", "Velocità e tonalità (Rubber Band)")
        import pedalboard

        stretched = pedalboard.time_stretch(
            np.ascontiguousarray(mix.T),
            SAMPLE_RATE,
            stretch_factor=rate,
            pitch_shift_in_semitones=semitones,
        )
        mix = np.ascontiguousarray(np.asarray(stretched, dtype=np.float32).T)
    ctx.progress(0.8)

    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > PEAK_LIMIT:
        mix = mix * (PEAK_LIMIT / peak)

    ctx.stage(JobStatus.ANALYZING, "write", "Scrittura del file")
    out_dir = export_dir(storage)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / f"{ctx.job_id}.wav"
    sf.write(str(wav), mix, SAMPLE_RATE, subtype="PCM_16")
    final = wav
    if fmt == "mp3":
        final = out_dir / f"{ctx.job_id}.mp3"
        _to_mp3(settings, db, song_id, wav, final, payload)
        wav.unlink(missing_ok=True)

    with db.read_session() as s:
        song = s.get(Song, song_id)
        title = song.title if song else "brano"
    suffix = []
    if abs(rate - 1.0) > 1e-3:
        suffix.append(f"{rate:.2f}x")
    if abs(semitones) > 1e-3:
        suffix.append(f"{semitones:+.0f}st")
    name = safe_filename(f"{title} - mix{(' ' + ' '.join(suffix)) if suffix else ''}{final.suffix}")
    ctx.run_phase(
        "result",
        lambda: {
            "path": storage.to_relative(final),
            "filename": name,
            "peak_reduced": peak > PEAK_LIMIT,
        },
    )
    ctx.progress(1.0, eta_s=0)


def _to_mp3(
    settings: Settings, db: Database, song_id: str, wav: Path, out: Path, payload: dict[str, Any]
) -> None:
    tools = MediaTools.from_settings(settings)
    with db.read_session() as s:
        song = s.get(Song, song_id)
    meta: list[str] = []
    if song is not None:
        comment = " · ".join(
            x
            for x in (
                f"Tonalità {payload.get('key_label') or song.key}"
                if (payload.get("key_label") or song.key)
                else None,
                f"Capo {payload.get('capo')}" if payload.get("capo") else None,
                f"BPM {song.bpm:.0f}" if song.bpm else None,
            )
            if x
        )
        for k, v in (
            ("title", song.title),
            ("artist", song.artist),
            ("album", song.album),
            ("comment", comment),
        ):
            if v:
                meta += ["-metadata", f"{k}={v}"]
    proc = subprocess.run(
        [
            str(tools.ffmpeg),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            str(wav),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "320k",
            "-id3v2_version",
            "3",
            *meta,
            str(out),
        ],
        capture_output=True,
        creationflags=_NO_WINDOW,
        check=False,
    )
    if proc.returncode != 0:
        raise JobError(
            "export_failed",
            "Conversione in MP3 non riuscita.",
            {"ffmpeg": proc.stderr.decode("utf-8", "replace")[-500:]},
        )
