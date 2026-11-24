"""Trascrizione polifonica di note con il modello Basic Pitch (Spotify) in ONNX Runtime.

Porting dell'inferenza e della creazione delle note di ``basic-pitch`` 0.4.0
(https://github.com/spotify/basic-pitch, licenza Apache-2.0): il pacchetto Python richiede
TensorFlow < 2.15.1, che non esiste per Python 3.12, ma contiene il modello in ONNX. Qui si
usano lo stesso modello, le stesse costanti e lo stesso algoritmo di creazione delle note
(``output_to_notes_polyphonic`` con "melodia trick"); manca solo il pitch bend, che alle tab
non serve.

Il modello (``nmp.onnx``, 225 KB) si scarica su richiesta dal wheel ufficiale su PyPI,
verificandone lo SHA-256.
"""

from __future__ import annotations

import hashlib
import io
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import numpy.typing as npt
import scipy.signal

from app.errors import AppError

# Costanti di basic_pitch/constants.py
FFT_HOP = 256
AUDIO_SAMPLE_RATE = 22050
AUDIO_WINDOW_LENGTH = 2
ANNOTATIONS_FPS = AUDIO_SAMPLE_RATE // FFT_HOP
ANNOT_N_FRAMES = ANNOTATIONS_FPS * AUDIO_WINDOW_LENGTH
AUDIO_N_SAMPLES = AUDIO_SAMPLE_RATE * AUDIO_WINDOW_LENGTH - FFT_HOP
MIDI_OFFSET = 21
MAX_FREQ_IDX = 87
N_OVERLAPPING_FRAMES = 30
OVERLAP_LEN = N_OVERLAPPING_FRAMES * FFT_HOP
HOP_SIZE = AUDIO_N_SAMPLES - OVERLAP_LEN

# Parametri predefiniti di basic_pitch.inference.predict
ONSET_THRESHOLD = 0.5
FRAME_THRESHOLD = 0.3
MIN_NOTE_LEN_FRAMES = int(np.round(127.70 / 1000 * (AUDIO_SAMPLE_RATE / FFT_HOP)))
ENERGY_TOL = 11

WHEEL_URL = (
    "https://files.pythonhosted.org/packages/99/0e/"
    "3a36d22562daeb0ae3c78ac78da3f8dba96543c5576ed57d4acb8ddbab5b/"
    "basic_pitch-0.4.0-py2.py3-none-any.whl"
)
WHEEL_SHA256 = "738adb503aae7fdfc7d1e1511aa0ce35052315f260a19531ef4c356708425db0"
MODEL_MEMBER = "basic_pitch/saved_models/icassp_2022/nmp.onnx"
MODEL_FILENAME = "nmp.onnx"
DOWNLOAD_SIZE_KB = 700

FloatArray = npt.NDArray[np.float32]


@dataclass(frozen=True)
class NoteEvent:
    start_s: float
    end_s: float
    pitch_midi: int
    amplitude: float


def model_path(data_dir: Path) -> Path:
    return data_dir / "models" / "basic_pitch" / MODEL_FILENAME


def ensure_model(data_dir: Path) -> Path:
    """Scarica il modello se manca (wheel ufficiale, SHA-256 verificato)."""
    target = model_path(data_dir)
    if target.is_file():
        return target
    try:
        with urllib.request.urlopen(WHEEL_URL, timeout=60) as resp:
            data = resp.read()
    except OSError as exc:
        raise AppError("network_error", "Download del modello per le tab non riuscito.") from exc
    if hashlib.sha256(data).hexdigest() != WHEEL_SHA256:
        raise AppError("model_download_failed", "Il modello scaricato per le tab non è integro.")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        model = zf.read(MODEL_MEMBER)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")
    tmp.write_bytes(model)
    tmp.replace(target)
    return target


class BasicPitch:
    def __init__(self, onnx_path: Path) -> None:
        import onnxruntime as ort

        self.session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        names = {o.name for o in self.session.get_outputs()}
        # Mappatura dell'implementazione originale (note, onset, contour).
        wanted = [
            "StatefulPartitionedCall:1",
            "StatefulPartitionedCall:2",
            "StatefulPartitionedCall:0",
        ]
        if not set(wanted) <= names:
            raise AppError("tab_model_invalid", "Il modello per le tab non ha il formato atteso.")
        self.output_names = wanted

    def infer(self, audio: FloatArray, check: Callable[[], None]) -> dict[str, FloatArray]:
        """``audio``: mono a 22 050 Hz. Restituisce note e onset (n_frame x 88)."""
        original_length = audio.shape[0]
        padded = np.concatenate([np.zeros(OVERLAP_LEN // 2, dtype=np.float32), audio])
        notes: list[FloatArray] = []
        onsets: list[FloatArray] = []
        for start in range(0, padded.shape[0], HOP_SIZE):
            check()
            window = padded[start : start + AUDIO_N_SAMPLES]
            if window.shape[0] < AUDIO_N_SAMPLES:
                window = np.pad(window, (0, AUDIO_N_SAMPLES - window.shape[0]))
            x = window.reshape(1, AUDIO_N_SAMPLES, 1).astype(np.float32)
            note, onset, _contour = self.session.run(self.output_names, {self.input_name: x})
            notes.append(np.asarray(note))
            onsets.append(np.asarray(onset))
        return {
            "note": _unwrap(np.concatenate(notes), original_length),
            "onset": _unwrap(np.concatenate(onsets), original_length),
        }


def _unwrap(output: FloatArray, original_length: int) -> FloatArray:
    n_olap = N_OVERLAPPING_FRAMES // 2
    output = output[:, n_olap:-n_olap, :]
    n_frames = int(np.floor(original_length * (ANNOTATIONS_FPS / AUDIO_SAMPLE_RATE)))
    flat = output.reshape(output.shape[0] * output.shape[1], output.shape[2])
    return np.asarray(flat[:n_frames, :], dtype=np.float32)


def _model_frames_to_time(n_frames: int) -> npt.NDArray[np.float64]:
    original = librosa.frames_to_time(np.arange(n_frames), sr=AUDIO_SAMPLE_RATE, hop_length=FFT_HOP)
    window_numbers = np.floor(np.arange(n_frames) / ANNOT_N_FRAMES)
    window_offset = (FFT_HOP / AUDIO_SAMPLE_RATE) * (
        ANNOT_N_FRAMES - (AUDIO_N_SAMPLES / FFT_HOP)
    ) + 0.0018
    return np.asarray(original - (window_offset * window_numbers), dtype=np.float64)


def _inferred_onsets(onsets: FloatArray, frames: FloatArray, n_diff: int = 2) -> FloatArray:
    diffs = []
    for n in range(1, n_diff + 1):
        appended = np.concatenate([np.zeros((n, frames.shape[1])), frames])
        diffs.append(appended[n:, :] - appended[:-n, :])
    frame_diff = np.min(diffs, axis=0)
    frame_diff[frame_diff < 0] = 0
    frame_diff[:n_diff, :] = 0
    top = np.max(frame_diff)
    if top > 0:
        frame_diff = np.max(onsets) * frame_diff / top
    return np.asarray(np.max([onsets, frame_diff], axis=0), dtype=np.float32)


def notes_from_output(
    output: dict[str, FloatArray],
    min_midi: int | None = None,
    max_midi: int | None = None,
    check: Callable[[], None] | None = None,
) -> list[NoteEvent]:
    """``output_to_notes_polyphonic`` di basic-pitch (con inferenza degli onset e melodia trick)."""
    frames = output["note"].copy()
    onsets = output["onset"].copy()
    n_frames = frames.shape[0]
    if max_midi is not None:
        onsets[:, max_midi - MIDI_OFFSET + 1 :] = 0
        frames[:, max_midi - MIDI_OFFSET + 1 :] = 0
    if min_midi is not None:
        onsets[:, : max(min_midi - MIDI_OFFSET, 0)] = 0
        frames[:, : max(min_midi - MIDI_OFFSET, 0)] = 0
    onsets = _inferred_onsets(onsets, frames)

    peak_mat = np.zeros(onsets.shape)
    peaks = scipy.signal.argrelmax(onsets, axis=0)
    peak_mat[peaks] = onsets[peaks]
    onset_idx = np.where(peak_mat >= ONSET_THRESHOLD)
    onset_time_idx = onset_idx[0][::-1]
    onset_freq_idx = onset_idx[1][::-1]

    remaining = frames.astype(np.float64).copy()
    events: list[tuple[int, int, int, float]] = []
    for start, freq in zip(onset_time_idx, onset_freq_idx, strict=True):
        if start >= n_frames - 1:
            continue
        i, k = start + 1, 0
        while i < n_frames - 1 and k < ENERGY_TOL:
            k = k + 1 if remaining[i, freq] < FRAME_THRESHOLD else 0
            i += 1
        i -= k
        if i - start <= MIN_NOTE_LEN_FRAMES:
            continue
        remaining[start:i, freq] = 0
        if freq < MAX_FREQ_IDX:
            remaining[start:i, freq + 1] = 0
        if freq > 0:
            remaining[start:i, freq - 1] = 0
        events.append(
            (int(start), int(i), int(freq) + MIDI_OFFSET, float(np.mean(frames[start:i, freq])))
        )

    # melodia trick: note senza onset netto a partire dai massimi di energia residua
    shape = remaining.shape
    steps = 0
    while np.max(remaining) > FRAME_THRESHOLD:
        steps += 1
        if check is not None and steps % 200 == 0:
            check()
        i_mid, freq = np.unravel_index(np.argmax(remaining), shape)
        remaining[i_mid, freq] = 0
        i, k = i_mid + 1, 0
        while i < n_frames - 1 and k < ENERGY_TOL:
            k = k + 1 if remaining[i, freq] < FRAME_THRESHOLD else 0
            _clear(remaining, i, int(freq))
            i += 1
        i_end = i - 1 - k
        i, k = i_mid - 1, 0
        while i > 0 and k < ENERGY_TOL:
            k = k + 1 if remaining[i, freq] < FRAME_THRESHOLD else 0
            _clear(remaining, i, int(freq))
            i -= 1
        i_start = i + 1 + k
        if i_end - i_start <= MIN_NOTE_LEN_FRAMES:
            continue
        events.append(
            (
                int(i_start),
                int(i_end),
                int(freq) + MIDI_OFFSET,
                float(np.mean(frames[i_start:i_end, freq])),
            )
        )

    times = _model_frames_to_time(n_frames)
    out = [
        NoteEvent(
            round(float(times[s]), 4), round(float(times[min(e, n_frames - 1)]), 4), p, round(a, 3)
        )
        for s, e, p, a in events
    ]
    out.sort(key=lambda n: (n.start_s, n.pitch_midi))
    return out


def _clear(remaining: npt.NDArray[np.float64], i: Any, freq: Any) -> None:
    remaining[i, freq] = 0
    if freq < MAX_FREQ_IDX:
        remaining[i, freq + 1] = 0
    if freq > 0:
        remaining[i, freq - 1] = 0


def load_audio(path: Path) -> FloatArray:
    y, _sr = librosa.load(str(path), sr=AUDIO_SAMPLE_RATE, mono=True)
    return np.asarray(y, dtype=np.float32)
