# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

from pynicotine.digging.maintenance import sweep, wipe
from pynicotine.digging.settings import DiggingSettings


def _settings(tmp_path):

    settings = DiggingSettings(work_dir=str(tmp_path / "work"), output_dir=str(tmp_path / "out"))
    (settings.work_path / "previews").mkdir(parents=True)
    (settings.work_path / "exports").mkdir(parents=True)
    return settings


def test_sweep_removes_orphan_previews(tmp_path):

    settings = _settings(tmp_path)
    stray = settings.work_path / "previews" / "stray.mp3"
    stray.write_bytes(b"x" * 2048)
    export = settings.work_path / "exports" / "old.wav"
    export.write_bytes(b"y" * 1024)

    report = sweep(settings)

    assert report.files_removed >= 1
    assert report.bytes_freed >= 2048
    assert not stray.exists()
    # exports are only evicted over budget, so this one stays
    assert export.exists()


def test_wipe_clears_everything(tmp_path):

    settings = _settings(tmp_path)
    (settings.work_path / "previews" / "a.mp3").write_bytes(b"x" * 100)
    (settings.work_path / "exports" / "b.wav").write_bytes(b"y" * 100)

    report = wipe(settings)

    assert report.files_removed == 2
    assert not (settings.work_path / "previews").exists()
    assert not (settings.work_path / "exports").exists()
