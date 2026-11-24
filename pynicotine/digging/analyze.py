# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Audio analysis for auditioning and Live Set generation.

ffmpeg/ffprobe do the decoding; numpy is optional and only needed for tempo
detection and waveform peaks (both degrade gracefully without it).
"""

from __future__ import annotations

import json
import shutil
import subprocess

from dataclasses import dataclass
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

AUDIO_EXTENSIONS = {
    ".aiff", ".aif", ".alac", ".ape", ".flac", ".m4a", ".m4b", ".mp3", ".mpc",
    ".ogg", ".oga", ".opus", ".wav", ".wma", ".wv",
}

NATURAL_KEYS = ("minor", "major")


class AnalysisError(Exception):
    pass


@dataclass(frozen=True)
class AudioInfo:
    path: Path
    duration: float          # seconds
    sample_rate: int
    channels: int
    codec: str
    bitrate: int             # bits per second, 0 when unknown
    frames: int              # samples per channel at sample_rate

    @property
    def size_mb(self) -> float:
        try:
            return self.path.stat().st_size / (1024 * 1024)
        except OSError:
            return 0.0


def is_audio_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in AUDIO_EXTENSIONS


def probe(path: str | Path) -> AudioInfo:
    """Read stream metadata with ffprobe."""

    target = Path(path)

    if not target.is_file():
        raise AnalysisError(f"not a file: {target}")

    cmd = [
        FFPROBE, "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=sample_rate,channels,codec_name,bit_rate,duration",
        "-show_entries", "format=duration,bit_rate",
        "-of", "json", str(target),
    ]

    try:
        completed = subprocess.run(cmd, capture_output=True, check=True, timeout=120)

    except (OSError, subprocess.SubprocessError) as error:
        raise AnalysisError(f"ffprobe failed for {target.name}: {error}") from error

    payload = json.loads(completed.stdout or b"{}")
    streams = payload.get("streams") or []
    container = payload.get("format") or {}

    if not streams:
        raise AnalysisError(f"no audio stream in {target.name}")

    stream = streams[0]
    sample_rate = int(stream.get("sample_rate") or 44100)
    duration = float(stream.get("duration") or container.get("duration") or 0.0)

    return AudioInfo(
        path=target,
        duration=duration,
        sample_rate=sample_rate,
        channels=int(stream.get("channels") or 2),
        codec=str(stream.get("codec_name") or "unknown"),
        bitrate=int(stream.get("bit_rate") or container.get("bit_rate") or 0),
        frames=int(round(duration * sample_rate)),
    )


def _decode_mono(path: Path, sample_rate: int):
    """Decode to a mono float32 numpy array, raising AnalysisError on failure."""

    try:
        import numpy as np

    except ImportError as error:
        raise AnalysisError("numpy is required for audio analysis") from error

    cmd = [
        FFMPEG, "-v", "error", "-i", str(path),
        "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "-",
    ]

    try:
        completed = subprocess.run(cmd, capture_output=True, check=True, timeout=300)

    except (OSError, subprocess.SubprocessError) as error:
        raise AnalysisError(f"ffmpeg decode failed for {path.name}: {error}") from error

    return np.frombuffer(completed.stdout, dtype="<f4")


def waveform_peaks(path: str | Path, buckets: int = 512) -> list[float]:
    """Return normalised peak amplitudes for drawing a waveform overview."""

    import numpy as np

    samples = _decode_mono(Path(path), 8000)

    if len(samples) == 0:
        return []

    chunk = max(1, len(samples) // max(1, buckets))
    usable = (len(samples) // chunk) * chunk
    values = np.abs(samples[:usable]).reshape(-1, chunk).max(axis=1)
    peak = float(values.max()) or 1.0

    return [round(float(value) / peak, 4) for value in values]


def detect_tempo(path: str | Path, min_bpm: float = 70.0, max_bpm: float = 180.0) -> tuple[float, float]:
    """Estimate track tempo from an onset envelope.

    Returns a (bpm, confidence) tuple. Confidence is the normalised
    autocorrelation peak; low values mean the estimate should not be trusted.
    """

    import numpy as np

    sample_rate = 22050
    hop = 256
    samples = _decode_mono(Path(path), sample_rate)

    if len(samples) < sample_rate * 4:
        raise AnalysisError("track is too short for tempo detection")

    frame = 1024
    frames = 1 + (len(samples) - frame) // hop

    if frames < 32:
        raise AnalysisError("track is too short for tempo detection")

    # RMS energy per frame, then a half-wave rectified difference = onsets
    energy = np.empty(frames, dtype=np.float32)
    windows = np.lib.stride_tricks.sliding_window_view(samples[:frame + hop * (frames - 1)], frame)[::hop]
    energy = np.sqrt(np.mean(windows * windows, axis=1))

    onset = np.diff(energy, prepend=energy[0])
    onset[onset < 0] = 0.0
    onset -= onset.mean()

    if not np.any(onset):
        return 0.0, 0.0

    correlation = np.correlate(onset, onset, mode="full")[len(onset) - 1:]

    if correlation[0] > 0:
        correlation = correlation / correlation[0]

    frame_rate = sample_rate / hop
    min_lag = int(frame_rate * 60.0 / max_bpm)
    max_lag = int(frame_rate * 60.0 / min_bpm)

    if max_lag >= len(correlation):
        max_lag = len(correlation) - 1

    if min_lag < 1 or max_lag <= min_lag:
        raise AnalysisError("tempo range does not fit the analysed audio")

    window = correlation[min_lag:max_lag + 1]
    peak_index = int(np.argmax(window))
    best_lag = min_lag + peak_index
    confidence = float(window[peak_index])

    # Parabolic interpolation around the peak for sub-frame accuracy
    if 0 < best_lag < len(correlation) - 1:
        left = float(correlation[best_lag - 1])
        center = float(correlation[best_lag])
        right = float(correlation[best_lag + 1])
        denominator = left - (2.0 * center) + right

        if denominator:
            offset = 0.5 * (left - right) / denominator
            best_lag = best_lag + offset

    bpm = 60.0 * frame_rate / best_lag

    while bpm < min_bpm:
        bpm *= 2

    while bpm > max_bpm:
        bpm /= 2

    return round(bpm, 2), round(min(1.0, max(0.0, confidence)), 4)


def beats_for_seconds(seconds: float, bpm: float) -> float:
    if not bpm:
        return 0.0

    return seconds * bpm / 60.0


def bars_for_seconds(seconds: float, bpm: float, beats_per_bar: int = 4) -> float:
    if not bpm:
        return 0.0

    return beats_for_seconds(seconds, bpm) / beats_per_bar


def describe(path: str | Path) -> dict:
    """Human-readable metadata blob used by the CLI and the pipeline."""

    info = probe(path)
    bpm, confidence = 0.0, 0.0

    try:
        bpm, confidence = detect_tempo(path)

    except AnalysisError:
        pass

    return {
        "path": str(info.path),
        "duration": round(info.duration, 3),
        "sample_rate": info.sample_rate,
        "channels": info.channels,
        "codec": info.codec,
        "bitrate_kbps": int(info.bitrate / 1000),
        "frames": info.frames,
        "bpm": bpm,
        "bpm_confidence": confidence,
        "bars": round(bars_for_seconds(info.duration, bpm), 2),
    }
