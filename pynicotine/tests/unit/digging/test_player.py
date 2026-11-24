# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

import math
import struct
import wave

import pytest

from pynicotine.digging.audition import player


def _write_tone(path, seconds=1.0, rate=44100):

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(
            struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * index / rate)))
            for index in range(int(rate * seconds))
        ))


def test_decode_and_peaks(tmp_path):

    target = tmp_path / "tone.wav"
    _write_tone(target)

    audio = player.decode(target, sample_rate=44100, channels=1)

    assert len(audio) == pytest.approx(44100, abs=500)

    values = player.peaks(audio, buckets=32)

    assert len(values) == 32
    assert max(values) == pytest.approx(1.0)


def test_player_position_and_seek(tmp_path):

    target = tmp_path / "tone.wav"
    _write_tone(target, seconds=3.0)

    playback = player.Player()
    duration = playback.load(target)

    assert duration == pytest.approx(3.0, abs=0.05)
    assert playback.position == 0.0

    playback.seek(1.5)
    assert playback.position == pytest.approx(1.5, abs=0.01)

    playback.seek(99.0)
    assert playback.position == pytest.approx(3.0, abs=0.05)

    playback.seek(-5.0)
    assert playback.position == 0.0
