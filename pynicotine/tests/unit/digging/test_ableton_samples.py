# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

import wave

from pynicotine.digging import ableton


def _make_wav(path, seconds=1, rate=44100):

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * rate * seconds)


def test_collect_samples_copies_and_repoints(tmp_path):

    source = tmp_path / "source"
    source.mkdir()
    stem = source / "vocals.wav"
    _make_wav(stem)

    xml = (
        "<LiveSet><Tracks><AudioClip><SampleRef><FileRef>"
        '<RelativePathType Value="3" />'
        '<RelativePath Value="Samples/Collected/vocals.wav" />'
        f'<Path Value="{stem}" />'
        '<Type Value="2" />'
        '<OriginalFileSize Value="0" />'
        "</FileRef></SampleRef></AudioClip></Tracks></LiveSet>"
    )

    out_dir = tmp_path / "set"
    result = ableton._collect_samples(xml, out_dir, {"vocals": stem})

    collected = out_dir / "Samples" / "Collected" / "vocals.wav"

    assert collected.is_file()
    assert f'<Path Value="{collected.resolve()}" />' in result
    assert '<RelativePathType Value="0" />' in result
    assert '<RelativePath Value="" />' in result
    assert f'<OriginalFileSize Value="{collected.stat().st_size}" />' in result
