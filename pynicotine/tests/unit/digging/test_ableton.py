# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

import gzip
import re

from pathlib import Path

import pytest

from pynicotine.digging import ableton


def test_warp_markers_define_tempo():

    clip = "<AudioClip><WarpMode Value=\"0\" /><WarpMarkers><WarpMarker Id=\"1\" SecTime=\"0\" BeatTime=\"0\" /></WarpMarkers></AudioClip>"
    updated = ableton._warp_markers(clip, 120.0, index=2)

    assert 'SecTime="0.500000000"' in updated
    assert 'BeatTime="1"' in updated
    assert 'Id="40004"' in updated
    assert 'Id="40005"' in updated
    assert updated.count("<WarpMarker ") == 2


def test_warp_markers_are_unique_per_clip():

    clip = "<AudioClip><WarpMarkers /></AudioClip>"
    first = ableton._warp_markers(clip, 90.0, index=0)
    second = ableton._warp_markers(clip, 90.0, index=1)

    assert first != second


def test_sanitize_name():

    assert ableton._sanitize("Kool & The Gang - Summer Madness") == "Kool-The-Gang-Summer-Madness"
    assert ableton._sanitize("...") == "Digging"
    assert ableton._sanitize("x" * 200) != ""
    assert len(ableton._sanitize("x" * 200)) <= 100


def test_rewrite_warp_enables_clip(tmp_path):

    xml = "<Ableton><Tracks><AudioClip><IsWarped Value=\"false\" /><WarpMode Value=\"0\" /><WarpMarkers /></AudioClip></Tracks></Ableton>"
    target = tmp_path / "set.als"

    with gzip.open(target, "wb") as handle:
        handle.write(xml.encode())

    ableton._rewrite_warp(target, 100.0, {"vocals": "complex_pro"})
    result = gzip.decompress(target.read_bytes()).decode()

    assert '<IsWarped Value="true" />' in result
    assert '<WarpMode Value="5" />' in result
    assert 'SecTime="0.600000000"' in result


@pytest.mark.skipif(not Path.home().joinpath("Documents/ALS Observatory/src/als_observatory").is_dir(),
                    reason="ALS Observatory checkout not present")
def test_build_live_set_end_to_end(tmp_path):

    from pynicotine.digging.settings import DiggingSettings

    settings = DiggingSettings(work_dir=str(tmp_path / "work"), output_dir=str(tmp_path / "out"))
    stems = {}

    import math
    import struct
    import wave

    for index, name in enumerate(("vocals", "instrumental")):
        path = tmp_path / f"{name}.wav"
        rate = 44100
        seconds = 2

        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(b"".join(
                struct.pack("<h", int(8000 * math.sin(2 * math.pi * (220 + index * 110) * t / rate)))
                for t in range(rate * seconds)
            ))

        stems[name] = path

    built = ableton.build_live_set(stems=stems, out_dir=tmp_path / "set", name="Test Set",
                                   bpm=128.0, settings=settings)

    assert built.path.is_file()
    assert built.warped
    xml = gzip.decompress(built.path.read_bytes()).decode()
    assert xml.count("<AudioTrack") == 2
    assert '<IsWarped Value="true" />' in xml
    assert re.search(r'<Tempo>.*?<Manual Value="128', xml, re.S)
