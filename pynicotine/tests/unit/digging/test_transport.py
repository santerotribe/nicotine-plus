# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Transport tests that drive Player.render() directly, with no audio device."""

from __future__ import annotations

import math
import struct
import time
import wave

import numpy as np
import pytest

from pynicotine.digging.audition.player import PlaybackFinished, Player


def _write_tone(path, freq=440.0, seconds=4.0, rate=44100):

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()

        for index in range(int(rate * seconds)):
            value = int(12000 * math.sin(2 * math.pi * freq * index / rate))
            frames += struct.pack("<hh", value, value)

        handle.writeframes(bytes(frames))

    return path


def _array(freq=220.0, seconds=2.0, rate=44100):

    t = np.arange(int(rate * seconds)) / rate
    mono = (0.3 * np.sin(2 * math.pi * freq * t)).astype("float32")
    return np.stack([mono, mono], axis=1)


def _wait_for(buffer, seconds=1.0, timeout=8.0):

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if buffer.frames >= int(seconds * buffer.sample_rate) or buffer.done:
            return True

        time.sleep(0.02)

    return False


def test_render_advances_and_finishes():

    playback = Player()
    playback.load_array(_array(seconds=0.5))
    playback.volume = 0.5

    block = playback.render(1024)

    assert block.shape == (1024, 2)
    assert playback.position == pytest.approx(1024 / 44100, rel=0.01)

    with pytest.raises(PlaybackFinished):
        while True:
            playback.render(4096)


def test_seek_clamps_and_offsets_audio():

    playback = Player()
    playback.load_array(_array(seconds=2.0))

    playback.seek(10.0)
    assert playback.position == pytest.approx(2.0, abs=0.01)

    playback.seek(1.0)
    first = playback.render(256)
    playback.seek(1.0)
    second = playback.render(256)

    assert np.allclose(first, second)


def test_stream_render_plays_buffered_audio(tmp_path):

    source = _write_tone(tmp_path / "tone.wav", seconds=3.0)
    playback = Player()
    playback.load_stream(source, duration_hint=3.0)
    buffer = playback._buffer

    try:
        assert _wait_for(buffer, 0.5)
        block = playback.render(2048)

        assert np.abs(block).max() > 0.0
        assert playback.position > 0.0
        assert 0.0 < playback.buffered_fraction <= 1.0

    finally:
        playback.stop()


def test_seek_beyond_buffer_clamps_without_reload(tmp_path):

    source = _write_tone(tmp_path / "tone.wav", seconds=3.0)
    playback = Player()
    playback.load_stream(source, duration_hint=3.0)

    try:
        assert _wait_for(playback._buffer, 0.5)

        decoded = playback._buffer.duration
        playback.seek(decoded + 5.0, reload=False)

        assert playback.position <= decoded + 0.01

    finally:
        playback.stop()


def test_adopt_crossfades_then_switches(tmp_path):

    source = _write_tone(tmp_path / "tone.wav", freq=880.0, seconds=4.0)
    playback = Player()
    playback.load_array(_array(freq=220.0, seconds=4.0))

    before = playback.render(1024)

    buffer, decoder = playback.preload_stream(source, duration_hint=4.0, start=0.0)
    assert _wait_for(buffer, 0.5)

    playback.adopt(buffer, decoder, start=0.0, duration_hint=4.0, fade_seconds=0.1)

    try:
        during = playback.render(1024)

        # Mix of old and new is not identical to the outgoing audio
        assert not np.allclose(before, during)

        # Let the fade finish, then output must be the incoming source
        for _ in range(20):
            playback.render(1024)

        after = playback.render(1024)
        assert np.abs(after).max() > 0.0

    finally:
        playback.stop()


def test_stop_clears_stream_state(tmp_path):

    source = _write_tone(tmp_path / "tone.wav")
    playback = Player()
    playback.load_stream(source, duration_hint=4.0)
    _wait_for(playback._buffer, 0.2)

    playback.stop()

    assert playback._buffer is None
    assert playback._decoder is None
    assert playback.position == 0.0