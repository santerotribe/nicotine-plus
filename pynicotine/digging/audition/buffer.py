# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Progressive audio buffering so playback can start before a track is fetched.

A decode thread streams ffmpeg's PCM output into a growing in-memory buffer; the
player reads from it and emits silence while the playhead catches up with the
data. Seeking beyond the buffered region restarts the decode at that offset.
"""

from __future__ import annotations

import shutil
import subprocess
import threading

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

READ_CHUNK = 1 << 18  # frames per pipe read (~6 s of float32 stereo)


class AudioBuffer:
    """A growable interleaved float32 buffer with concurrent append/read."""

    def __init__(self, sample_rate: int = 44100, channels: int = 2,
                 duration_hint: float = 0.0) -> None:

        import numpy as np

        self.sample_rate = sample_rate
        self.channels = channels
        self._np = np
        self._lock = threading.Lock()
        self._frames = 0
        self._done = False
        self._error = ""
        capacity = max(sample_rate * 30, int(max(0.0, duration_hint) * sample_rate) + sample_rate)
        self._data = np.zeros((capacity, channels), dtype="float32")

    def _ensure_capacity(self, frames: int) -> None:

        if frames <= len(self._data):
            return

        capacity = max(frames, len(self._data) * 2)
        grown = self._np.zeros((capacity, self.channels), dtype="float32")
        grown[:self._frames] = self._data[:self._frames]
        self._data = grown

    def append(self, block) -> None:
        """Append frames shaped (n, channels)."""

        with self._lock:
            start = self._frames
            end = start + len(block)
            self._ensure_capacity(end)
            self._data[start:end] = block
            self._frames = end

    def read(self, start: int, count: int):
        """Return (block, available) where block is count frames zero-padded."""

        with self._lock:
            frames = self._frames
            done = self._done

        if start >= frames:
            return None, 0, done

        end = min(frames, start + count)
        block = self._data[start:end].copy()

        if len(block) < count:
            padding = self._np.zeros((count - len(block), self.channels), dtype="float32")
            block = self._np.vstack([block, padding])

        return block, end - start, done

    def mark_done(self, error: str = "") -> None:
        with self._lock:
            self._done = True

            if error:
                self._error = error

    @property
    def frames(self) -> int:
        with self._lock:
            return self._frames

    @property
    def done(self) -> bool:
        with self._lock:
            return self._done

    @property
    def error(self) -> str:
        with self._lock:
            return self._error

    @property
    def duration(self) -> float:
        return self.frames / self.sample_rate

    def snapshot(self):
        """Contiguous copy of the buffered audio (for peak extraction/export)."""

        with self._lock:
            return self._data[:self._frames].copy()


class StreamDecoder:
    """Runs ffmpeg and feeds an AudioBuffer from a background thread."""

    def __init__(self, source: str, buffer: AudioBuffer, start: float = 0.0) -> None:
        self.source = str(source)
        self.buffer = buffer
        self.start_seconds = float(start)
        self._process = None
        self._thread = None
        self._cancelled = False

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="digging-decode")
        self._thread.start()

    def cancel(self) -> None:
        self._cancelled = True
        process = self._process

        if process is not None:
            try:
                process.kill()

            except OSError:
                pass

    def _command(self) -> list[str]:

        command = [FFMPEG, "-v", "error", "-nostdin"]

        if self.source.startswith(("http://", "https://")):
            command += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]

        if self.start_seconds:
            command += ["-ss", f"{self.start_seconds:.3f}"]

        command += [
            "-i", self.source,
            "-f", "f32le", "-acodec", "pcm_f32le",
            "-ac", str(self.buffer.channels), "-ar", str(self.buffer.sample_rate), "-",
        ]
        return command

    def _run(self) -> None:

        import numpy as np

        try:
            self._process = subprocess.Popen(
                self._command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
            )

        except OSError as error:
            self.buffer.mark_done(str(error))
            return

        assert self._process.stdout is not None
        frame_bytes = 4 * self.buffer.channels
        pending = b""

        while not self._cancelled:
            chunk = self._process.stdout.read(READ_CHUNK * frame_bytes)

            if not chunk:
                break

            pending += chunk
            usable = (len(pending) // frame_bytes) * frame_bytes

            if not usable:
                continue

            audio = np.frombuffer(pending[:usable], dtype="<f4")
            pending = pending[usable:]
            self.buffer.append(audio.reshape(-1, self.buffer.channels))

        self._process.wait()
        error = ""

        if self._process.returncode not in (0, None) and not self._cancelled:
            error = (self._process.stderr.read() or b"").decode("utf-8", "replace")[-200:]

        self.buffer.mark_done(error)
