# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""In-process audio playback for auditioning.

PortAudio (sounddevice) plays a decoded numpy buffer, which gives us instant
seeks and a sample-accurate playhead for the waveform. ffmpeg does the decoding
and accepts local paths, http(s) URLs and ffmpeg pseudo-protocols alike.
"""

from __future__ import annotations

import shutil
import subprocess
import threading

from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
DEFAULT_RATE = 44100
DEFAULT_CHANNELS = 2


class PlayerError(Exception):
    pass


def decode(source: str | Path, start: float = 0.0, duration: float | None = None,
           sample_rate: int = DEFAULT_RATE, channels: int = DEFAULT_CHANNELS):
    """Decode a file or URL into a float32 numpy array shaped (frames, channels)."""

    try:
        import numpy as np
        import sounddevice  # noqa: F401

    except ImportError as error:
        raise PlayerError("sounddevice/numpy are required for playback") from error

    target = str(source)
    command = [FFMPEG, "-v", "error", "-nostdin"]

    if target.startswith(("http://", "https://")):
        command += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]

    if start:
        command += ["-ss", f"{start:.3f}"]

    command += ["-i", target]

    if duration:
        command += ["-t", f"{duration:.3f}"]

    command += ["-f", "f32le", "-acodec", "pcm_f32le", "-ac", str(channels), "-ar", str(sample_rate), "-"]

    completed = subprocess.run(command, capture_output=True, timeout=120)

    if completed.returncode != 0:
        detail = (completed.stderr or b"").decode("utf-8", "replace").strip()[-300:]
        raise PlayerError(f"decode failed: {detail or 'no audio'}")

    audio = np.frombuffer(completed.stdout, dtype="<f4")

    if audio.size == 0:
        raise PlayerError("decode produced no audio")

    if channels > 1:
        audio = audio.reshape(-1, channels)

    return audio.copy()


def peaks(audio, buckets: int = 512) -> list[float]:
    """Normalised waveform peaks for a decoded buffer."""

    import numpy as np

    if audio is None or len(audio) == 0:
        return []

    mono = audio.mean(axis=1) if getattr(audio, "ndim", 1) > 1 else audio
    chunk = max(1, len(mono) // max(1, buckets))
    usable = (len(mono) // chunk) * chunk
    values = np.abs(mono[:usable]).reshape(-1, chunk).max(axis=1)
    peak = float(values.max()) or 1.0

    return [round(float(value) / peak, 4) for value in values]


class Player:
    """A single decoded buffer with play/pause/seek, driven by PortAudio."""

    def __init__(self, sample_rate: int = DEFAULT_RATE, channels: int = DEFAULT_CHANNELS) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.volume = 1.0
        self._audio = None
        self._stream = None
        self._position = 0
        self._lock = threading.Lock()
        self._on_finish = None

    # -- buffer -----------------------------------------------------------

    def load(self, source: str | Path, start: float = 0.0, duration: float | None = None) -> float:
        """Decode a source and make it ready to play. Returns its duration."""

        self.stop()
        audio = decode(source, start=start, duration=duration,
                       sample_rate=self.sample_rate, channels=self.channels)

        with self._lock:
            self._audio = audio
            self._position = 0

        return self.duration

    def load_array(self, audio) -> float:
        self.stop()

        with self._lock:
            self._audio = audio
            self._position = 0

        return self.duration

    @property
    def audio(self):
        """The decoded buffer backing the current playback (None when idle)."""

        return self._audio

    def peaks(self, buckets: int = 900) -> list[float]:
        """Waveform peaks for the currently loaded buffer."""

        return peaks(self._audio, buckets) if self._audio is not None else []

    @property
    def duration(self) -> float:
        audio = self._audio

        if audio is None:
            return 0.0

        return len(audio) / self.sample_rate

    @property
    def position(self) -> float:
        with self._lock:
            return self._position / self.sample_rate

    @property
    def is_playing(self) -> bool:
        return bool(self._stream is not None and self._stream.active)

    def set_finish_callback(self, callback) -> None:
        self._on_finish = callback

    # -- transport --------------------------------------------------------

    def play(self) -> None:
        if self._audio is None:
            raise PlayerError("nothing loaded")

        if self._stream is None:
            self._stream = self._create_stream()

        if not self._stream.active:
            self._stream.start()

    def pause(self) -> None:
        if self._stream is not None and self._stream.active:
            self._stream.stop()

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()

            except Exception:  # noqa: BLE001 - PortAudio raises various errors on close
                pass

            self._stream = None

        with self._lock:
            self._position = 0

    def seek(self, seconds: float) -> None:
        with self._lock:
            if self._audio is None:
                self._position = 0
                return

            self._position = max(0, min(len(self._audio) - 1, int(seconds * self.sample_rate)))

    def skip(self, delta: float) -> None:
        self.seek(self.position + delta)

    # -- internals --------------------------------------------------------

    def _create_stream(self):
        import sounddevice as sd

        return sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=0,
            callback=self._callback,
        )

    def _callback(self, outdata, frames, _time_info, status) -> None:  # noqa: ANN001
        import numpy as np
        import sounddevice as sd

        with self._lock:
            audio = self._audio

            if audio is None:
                outdata.fill(0)
                raise sd.CallbackStop

            start = self._position
            end = min(len(audio), start + frames)
            block = audio[start:end]
            written = len(block)

            if written:
                outdata[:written] = block * self.volume

            if written < frames:
                outdata[written:] = 0

            self._position = end
            finished = self._position >= len(audio)

        if finished:
            if self._on_finish:
                self._on_finish()

            raise sd.CallbackStop
