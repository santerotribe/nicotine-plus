# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

import pytest

from pynicotine.digging.renderers.base import RenderError, RenderRequest, guess_stem, organize


def test_guess_stem_matches_provider_names():

    assert guess_stem("Vocals.wav") == "vocals"
    assert guess_stem("01 - instrumental.flac") == "instrumental"
    assert guess_stem("htdemucs/drums.wav") == "drums"
    assert guess_stem("bass.wav") == "bass"
    assert guess_stem("Piano.wav") == "piano"
    assert guess_stem("guitar.wav") == "guitar"
    assert guess_stem("unknown-output.wav") == "other"


def test_organize_keeps_requested_preset():

    files = [Path("/x/vocals.wav"), Path("/x/drums.wav"), Path("/x/bass.wav"), Path("/x/other.wav")]
    stems = organize(files, "4")

    assert set(stems) == {"vocals", "drums", "bass", "other"}
    assert stems["vocals"].name == "vocals.wav"


def test_organize_two_stem_preset_ignores_extras():

    files = [Path("/x/vocals.wav"), Path("/x/instrumental.wav"), Path("/x/drums.wav")]
    stems = organize(files, "2")

    assert set(stems) == {"vocals", "instrumental"}


def test_render_request_validates(tmp_path):

    source = tmp_path / "song.wav"
    source.write_bytes(b"RIFF")

    request = RenderRequest(source=source, outdir=tmp_path / "out", preset="4")
    assert request.preset == "4"

    with pytest.raises(RenderError):
        RenderRequest(source=source, outdir=tmp_path / "out", preset="9")

    with pytest.raises(RenderError):
        RenderRequest(source=tmp_path / "missing.wav", outdir=tmp_path / "out", preset="4")
