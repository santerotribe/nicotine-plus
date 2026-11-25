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


class PlaybackFinished(Exception):
    """Raised by Player.render() when the current source has no more audio."""


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


def self_chunk(value, seconds: float = 0.5) -> int:
    """Rough frame count for a short analysis window (tolerates arrays/buffers)."""

    rate = getattr(value, "sample_rate", 44100)
    return max(1, int(seconds * rate))


def should_extend(position: float, duration: float, decoded: float, frames: int,
                  sample_rate: int, seconds_since_load: float, buffer_done: bool) -> bool:
    """Whether playback should reopen the growing file to fetch more audio.

    Guards the reload loop: right after a seek the buffer starts at the playhead,
    so an unguarded edge check would restart ffmpeg on every tick.
    """

    if buffer_done or duration <= 0 or decoded <= 0:
        return False

    if seconds_since_load < 3.0:
        return False

    if frames < int(1.0 * sample_rate):
        return False

    return position > decoded - 1.0 and position < duration - 0.5


class Player:
    """Decoded or progressively buffered audio with play/pause/seek (PortAudio)."""

    def __init__(self, sample_rate: int = DEFAULT_RATE, channels: int = DEFAULT_CHANNELS) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.volume = 1.0
        self._audio = None
        self._stream = None
        self._position = 0
        self._lock = threading.Lock()
        self._on_finish = None
        self._buffer = None
        self._decoder = None
        self._duration_hint = 0.0
        self._peaks_cache = None
        self._peaks_frames = -1
        self._peaks_time = 0.0
        self._stream_source = ""
        self._fade = None
        self._adopt_gain = 1.0

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

    def load_stream(self, source: str | Path, duration_hint: float = 0.0, start: float = 0.0) -> None:
        """Start buffered playback: audio begins as soon as the first chunk lands."""

        from pynicotine.digging.audition.buffer import AudioBuffer, StreamDecoder

        self.stop()
        buffer = AudioBuffer(self.sample_rate, self.channels, duration_hint, start_offset=start)
        decoder = StreamDecoder(str(source), buffer, start=start)
        decoder.start()

        with self._lock:
            self._audio = None
            self._buffer = buffer
            self._decoder = decoder
            self._stream_source = str(source)
            self._duration_hint = float(duration_hint or 0.0)
            self._position = int(start * self.sample_rate)
            self._peaks_cache = None
            self._peaks_frames = -1

    def preload_stream(self, source: str | Path, duration_hint: float = 0.0, start: float = 0.0):
        """Decode a stream in the background without disturbing playback.

        Returns (buffer, decoder) for a later adopt().
        """

        from pynicotine.digging.audition.buffer import AudioBuffer, StreamDecoder

        buffer = AudioBuffer(self.sample_rate, self.channels, duration_hint, start_offset=start)
        decoder = StreamDecoder(str(source), buffer, start=start)
        decoder.start()
        return buffer, decoder

    def adopt(self, buffer, decoder, start: float = 0.0, fade_seconds: float = 0.15,
              duration_hint: float = 0.0) -> None:
        """Atomically continue playback from a preloaded buffer, crossfading.

        The outgoing audio keeps playing for a few frames while the incoming
        buffer fades in, so switching from a catalogue preview to the peer's own
        file does not produce a click or a hole.
        """

        # Measure loudness before touching the lock: the audio callback is
        # mixing and must not wait on RMS math over a long buffer.
        old_buffer_for_gain = self._buffer
        old_audio_for_gain = self._audio
        incoming_gain = 1.0

        if fade_seconds > 0 and (old_buffer_for_gain is not None or old_audio_for_gain is not None):
            incoming_gain = self._match_gain(old_buffer_for_gain, old_audio_for_gain, buffer)

        with self._lock:
            old_buffer = self._buffer
            old_audio = self._audio
            old_position = self._position
            old_gain = 1.0

            if fade_seconds > 0 and (old_buffer is not None or old_audio is not None):
                self._fade = {
                    "buffer": old_buffer,
                    "audio": old_audio,
                    "position": old_position,
                    "frames": max(1, int(fade_seconds * self.sample_rate)),
                    "remaining": max(1, int(fade_seconds * self.sample_rate)),
                    "gain": old_gain,
                }
            else:
                self._fade = None
                incoming_gain = 1.0

            # Stop the outgoing decoder: it has served its frames
            if self._decoder is not None and self._decoder is not decoder:
                self._decoder.cancel()

            self._buffer = buffer
            self._decoder = decoder
            self._audio = None
            self._duration_hint = float(duration_hint or 0.0)
            self._position = int(start * self.sample_rate)
            self._peaks_cache = None
            self._peaks_frames = -1
            self._adopt_gain = incoming_gain

        if self._stream is None:
            self._stream = self._create_stream()

        if not self._stream.active:
            self._stream.start()

    @staticmethod
    def _match_gain(old_buffer, old_audio, new_buffer) -> float:
        """Scale the incoming audio to roughly the outgoing loudness."""

        import numpy as np

        try:
            if old_audio is not None:
                old = np.asarray(old_audio[:self_chunk(old_audio)])
            elif old_buffer is not None:
                old = old_buffer.snapshot()[:self_chunk(old_buffer.snapshot())]
            else:
                return 1.0

            new = new_buffer.snapshot()[: self_chunk(new_buffer)]

            if old.size == 0 or new.size == 0:
                return 1.0

            old_rms = float(np.sqrt(np.mean(old * old)))
            new_rms = float(np.sqrt(np.mean(new * new)))

            if old_rms < 1e-4 or new_rms < 1e-4:
                return 1.0

            return float(min(2.0, max(0.5, old_rms / new_rms)))

        except Exception:  # noqa: BLE001 - gain matching is cosmetic
            return 1.0

    def load_array(self, audio) -> float:
        self.stop()

        with self._lock:
            self._audio = audio
            self._position = 0

        return self.duration

    @property
    def audio(self):
        """Decoded audio for export: the full buffer, or everything fetched so far."""

        if self._buffer is not None:
            return self._buffer.snapshot()

        return self._audio

    @property
    def buffered_fraction(self) -> float:
        """How much of the track is decoded and seekable (1.0 when fully loaded)."""

        if self._buffer is None:
            return 1.0 if self._audio is not None else 0.0

        total = self._buffer.duration

        if not self._buffer.done and self._duration_hint:
            return max(0.0, min(1.0, total / self._duration_hint))

        if self._buffer.done and self._duration_hint:
            return 1.0

        return 1.0 if self._buffer.done else 0.0

    def peaks(self, buckets: int = 900) -> list[float]:
        """Waveform peaks for what is currently decoded (cached, grows over time)."""

        if self._audio is not None:
            return peaks(self._audio, buckets)

        if self._buffer is None:
            return []

        import time as _time

        frames = self._buffer.frames
        now = _time.monotonic()
        last_time = getattr(self, "_peaks_time", 0.0)

        if self._peaks_cache is not None and (frames == self._peaks_frames or now - last_time < 0.25):
            return self._peaks_cache

        self._peaks_cache = self._buffer.peaks(buckets)
        self._peaks_frames = frames
        self._peaks_time = now
        return self._peaks_cache

    @property
    def duration(self) -> float:
        if self._buffer is not None:
            return max(self._duration_hint, self._buffer.duration)

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
        if self._audio is None and self._buffer is None:
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

        decoder = self._decoder

        if decoder is not None:
            decoder.cancel()

        with self._lock:
            self._position = 0
            self._buffer = None
            self._decoder = None
            self._stream_source = ""
            self._duration_hint = 0.0
            self._peaks_cache = None
            self._peaks_frames = -1
            self._fade = None
            self._adopt_gain = 1.0

    def seek(self, seconds: float, reload: bool = True) -> None:
        """Seek within decoded audio, restarting the stream past what is buffered."""

        if self._buffer is not None:
            buffered = self._buffer.duration

            if seconds > buffered and not reload and not self._buffer.done:
                # Mid-drag: stay inside what we have instead of thrashing ffmpeg
                with self._lock:
                    self._position = max(0, int(buffered * self.sample_rate))

                return

            if self._buffer.done:
                # Nothing more will arrive: clamp instead of parking past the end
                with self._lock:
                    self._position = max(0, int(min(seconds, buffered) * self.sample_rate))

                return

            if seconds <= buffered:
                with self._lock:
                    self._position = max(0, int(seconds * self.sample_rate))
                return

            source = self._stream_source

            if not source:
                with self._lock:
                    self._position = max(0, int(buffered * self.sample_rate))
                return

            was_playing = self._stream is not None and self._stream.active
            self.load_stream(source, self._duration_hint, start=seconds)

            if was_playing:
                self.play()

            return

        with self._lock:
            if self._audio is None:
                self._position = 0
                return

            self._position = max(0, min(len(self._audio) - 1, int(seconds * self.sample_rate)))

    def skip(self, delta: float) -> None:
        self.seek(self.position + delta)

    # -- internals --------------------------------------------------------

    def _read_fade(self, fade, frames: int):
        """Frames from the outgoing source for the crossfade window."""

        old_buffer = fade.get("buffer")
        old_audio = fade.get("audio")
        position = int(fade.get("position", 0))
        available = 0

        if old_buffer is not None:
            block, available, _done = old_buffer.read(position - old_buffer.base_frames, frames)

        elif old_audio is not None:
            end = min(len(old_audio), position + frames)
            block = old_audio[position:end]
            available = len(block)

            if available < frames:
                import numpy as np

                pad = np.zeros((frames - available, old_audio.shape[1]), dtype="float32")
                block = np.vstack([block, pad])

        else:
            return None

        fade["position"] = position + frames
        return block if available else None

    def _create_stream(self):
        import sounddevice as sd

        return sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=0,
            callback=self._callback,
        )

    def render(self, frames: int):
        """Produce one block of output audio. Device-free, so it is testable.

        Raises PlaybackFinished when the current source is exhausted.
        """

        import numpy as np

        with self._lock:
            audio = self._audio
            buffer = self._buffer

        if buffer is not None:
            local = self._position - buffer.base_frames

            if local < 0:
                # Playhead sits before the buffered region (seeked backwards)
                return np.zeros((frames, self.channels), dtype="float32")

            block, available, done = buffer.read(local, frames)

            if block is None:
                if done:
                    raise PlaybackFinished

                return np.zeros((frames, self.channels), dtype="float32")

            mixed = block * (self.volume * self._adopt_gain)
            fade = self._fade

            if fade is not None:
                old_block = self._read_fade(fade, frames)

                if old_block is not None:
                    alpha = fade["remaining"] / fade["frames"]
                    incoming_gain = (self._adopt_gain * (1.0 - alpha)) + alpha
                    mixed = (block * self.volume * incoming_gain) + (old_block * alpha * self.volume)
                    fade["remaining"] = max(0, fade["remaining"] - frames)

                    if fade["remaining"] <= 0:
                        self._fade = None
                        self._adopt_gain = 1.0

            self._position = int(self._position + available)

            if available < frames and done:
                raise PlaybackFinished

            return mixed

        with self._lock:
            if audio is None:
                raise PlaybackFinished

            start = self._position
            end = min(len(audio), start + frames)
            block = audio[start:end]
            output = np.zeros((frames, self.channels), dtype="float32")
            written = len(block)

            if written:
                output[:written] = block * self.volume

            self._position = end
            finished = self._position >= len(audio)

        if finished:
            raise PlaybackFinished

        return output

    def _callback(self, outdata, frames, _time_info, _status) -> None:  # noqa: ANN001
        import sounddevice as sd

        try:
            block = self.render(frames)

        except PlaybackFinished:
            outdata.fill(0)

            if self._on_finish:
                self._on_finish()

            raise sd.CallbackStop

        outdata[:] = block
