# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

import threading
import time

from pynicotine.digging.actions import crate_for
from pynicotine.digging.crate import STATUS_KEPT, CrateTrack
from pynicotine.digging.service import PipelineService
from pynicotine.digging.settings import DiggingSettings


def _service(tmp_path):

    settings = DiggingSettings(work_dir=str(tmp_path / "work"), output_dir=str(tmp_path / "out"))
    settings.ensure_dirs()
    return PipelineService(settings), settings


def test_find_track_requires_kept_without_stems(tmp_path):

    service, settings = _service(tmp_path)
    crate = crate_for(settings)
    kept = crate.add(CrateTrack(username="dj", virtual_path="a\\b.flac", filename="b.flac",
                                status=STATUS_KEPT))

    assert service._find_track("dj", "a\\b.flac") is kept

    kept.stems = {"vocals": "/x"}
    crate.save()

    assert service._find_track("dj", "a\\b.flac") is None


def test_local_path_prefers_recorded_then_download_folder(tmp_path):

    service, settings = _service(tmp_path)
    track = CrateTrack(username="dj", virtual_path="a\\b.flac", filename="b.flac")

    assert service._local_path(track) is None

    downloaded = settings.work_path / "downloads" / "dj" / "b.flac"
    downloaded.parent.mkdir(parents=True)
    downloaded.write_bytes(b"audio")

    assert service._local_path(track) == downloaded


def test_kick_processes_downloaded_track(tmp_path, monkeypatch):

    service, settings = _service(tmp_path)
    crate = crate_for(settings)
    track = crate.add(CrateTrack(username="dj", virtual_path="a\\b.flac", filename="b.flac",
                                 status=STATUS_KEPT))

    downloaded = settings.work_path / "downloads" / "dj" / "b.flac"
    downloaded.parent.mkdir(parents=True)
    downloaded.write_bytes(b"audio")
    track.local_path = str(downloaded)
    crate.save()

    seen = []
    done = threading.Event()

    def fake_process(entry, path):
        seen.append((entry.id, path))
        done.set()

    monkeypatch.setattr(service, "_process", fake_process)
    service.kick(track)

    assert done.wait(3.0)
    assert seen and seen[0][0] == track.id


def test_kick_ignores_missing_file(tmp_path):

    service, _settings = _service(tmp_path)
    track = CrateTrack(username="dj", virtual_path="a\\b.flac", filename="b.flac",
                       status=STATUS_KEPT)

    service.kick(track)
    time.sleep(0.2)

    assert not service._running
