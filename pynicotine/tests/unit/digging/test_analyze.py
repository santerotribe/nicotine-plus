# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

import math
import struct
import wave

import pytest

from pynicotine.digging import analyze


def _write_click(path, bpm=120.0, seconds=8.0, sample_rate=44100):

    frames = int(seconds * sample_rate)
    interval = 60.0 / bpm
    samples = []

    for index in range(frames):
        moment = index / sample_rate
        phase = moment % interval
        value = 0.0

        if phase < 0.02:
            value = 0.6 * math.sin(2 * math.pi * 1000 * moment) * math.exp(-phase * 40)

        samples.append(int(max(-1.0, min(1.0, value)) * 32767))

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))


def test_probe_reports_duration(tmp_path):

    target = tmp_path / "click.wav"
    _write_click(target, seconds=4.0)

    info = analyze.probe(target)

    assert info.duration == pytest.approx(4.0, abs=0.05)
    assert info.channels == 1
    assert info.sample_rate == 44100
    assert info.frames == pytest.approx(176400, abs=100)


def test_detect_tempo_finds_click_track(tmp_path):

    target = tmp_path / "click.wav"
    _write_click(target, bpm=120.0, seconds=8.0)

    bpm, confidence = analyze.detect_tempo(target)

    assert bpm == pytest.approx(120.0, abs=2.0)
    assert confidence > 0.3


def test_waveform_peaks_are_normalised(tmp_path):

    target = tmp_path / "click.wav"
    _write_click(target, seconds=2.0)

    peaks = analyze.waveform_peaks(target, buckets=64)

    assert len(peaks) == 64
    assert max(peaks) == pytest.approx(1.0)
    assert min(peaks) >= 0.0


def test_is_audio_file():

    assert analyze.is_audio_file("song.FLAC")
    assert analyze.is_audio_file("song.mp3")
    assert not analyze.is_audio_file("cover.jpg")
