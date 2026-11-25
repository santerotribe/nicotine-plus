# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

from pynicotine.digging.settings import STEM_PRESETS, DiggingSettings, renderer_available


def test_defaults_are_populated():

    settings = DiggingSettings()

    assert settings.preset in STEM_PRESETS
    assert settings.work_dir
    assert settings.observatory_root.endswith("ALS Observatory")
    assert settings.stems == STEM_PRESETS["4"]


def test_stem_presets_follow_setting():

    settings = DiggingSettings(preset="2")
    assert settings.stems == ("vocals", "instrumental")

    settings.preset = "6"
    assert "guitar" in settings.stems


def test_save_and_load_roundtrip(tmp_path):

    path = tmp_path / "digging.json"
    settings = DiggingSettings(renderer="pc", pc_url="http://studio:8765", preset="6",
                               warp_stems=False)
    settings.save(path)

    loaded = DiggingSettings.load(path)

    assert loaded.renderer == "pc"
    assert loaded.pc_url == "http://studio:8765"
    assert loaded.preset == "6"
    assert loaded.warp_stems is False


def test_load_missing_file_returns_defaults(tmp_path):

    loaded = DiggingSettings.load(tmp_path / "nope.json")
    assert loaded.renderer == "mvsep"

def test_renderer_available_reports_missing_configuration():

    settings = DiggingSettings()
    settings.renderer = "mvsep"
    settings.mvsep_token = ""
    ready, reason = renderer_available("mvsep", settings)
    assert not ready and "token" in reason.lower()

    settings.mvsep_token = "token"
    settings.mvsep_sep_type = ""
    ready, reason = renderer_available("mvsep", settings)
    assert not ready and "type" in reason.lower()

    settings.mvsep_sep_type = "51"
    assert renderer_available("mvsep", settings)[0]

    settings.pc_url = ""
    ready, reason = renderer_available("pc", settings)
    assert not ready and "address" in reason.lower()

    settings.pc_url = "http://studio:8765"
    assert renderer_available("pc", settings)[0]


def test_renderer_available_local_reports_binary():
    ready, reason = renderer_available("local", DiggingSettings())
    assert isinstance(ready, bool)

    if not ready:
        assert reason
