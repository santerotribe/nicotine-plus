# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from pynicotine.digging.settings import (
    DiggingSettings,
    apply_settings,
    public_settings,
)


def test_public_settings_masks_secrets_and_reports_readiness():

    settings = DiggingSettings(mvsep_token="secret", pc_token="")
    payload = public_settings(settings)

    assert "mvsep_token" not in payload
    assert payload["mvsep_token_set"] is True
    assert payload["pc_token_set"] is False
    assert set(payload["renderer_available"]) == {"mvsep", "pc", "local"}
    assert "warp_modes" in payload
    assert "presets" in payload


def test_apply_settings_accepts_a_valid_patch():

    settings = DiggingSettings()
    apply_settings(settings, {
        "renderer": "pc",
        "pc_url": "http://studio:8765",
        "warp_mode": "beats",
        "member_name": "mara",
        "preview_cache_mb": 1024,
        "warp_stems": False,
    })

    assert settings.renderer == "pc"
    assert settings.pc_url == "http://studio:8765"
    assert settings.warp_mode == "beats"
    assert settings.member_name == "mara"
    assert settings.preview_cache_mb == 1024
    assert settings.warp_stems is False


@pytest.mark.parametrize("payload", [
    {"renderer": "magic"},
    {"preset": "9"},
    {"warp_mode": "wobble"},
    {"preview_cache_mb": -1},
    {"warp_stems": "yes"},
    {"member_name": "  "},
    {"nonsense": 1},
])
def test_apply_settings_rejects_bad_values(payload):

    with pytest.raises(ValueError):
        apply_settings(DiggingSettings(), payload)
