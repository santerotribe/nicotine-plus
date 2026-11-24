# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

from pynicotine.digging.audition.peer import PeerPreview, _status_text


def test_status_text_reports_queue_position():

    assert "privileged" in _status_text("Queued (privileged)", 3)
    assert "#3" in _status_text("Queued (privileged)", 3)
    assert _status_text("Queued", 0) == "queued"
    assert _status_text("Transferring", 0) == "downloading from peer"


def test_promote_copies_finished_file(tmp_path):

    finished = tmp_path / "cache" / "track.flac"
    finished.parent.mkdir()
    finished.write_bytes(b"audio-bytes")

    preview = PeerPreview("dj", "Music\\track.flac", "track.flac", 11, None, tmp_path / "cache")
    preview.finished_path = str(finished)

    target = preview.promote(tmp_path / "downloads")
    assert target is not None
    assert target == tmp_path / "downloads" / "track.flac"
    assert target.read_bytes() == b"audio-bytes"


def test_promote_waits_for_finish(tmp_path):

    preview = PeerPreview("dj", "Music\\track.flac", "track.flac", 11, None, tmp_path / "cache")
    preview.finished_path = ""

    assert preview.promote(tmp_path / "downloads") is None
    assert preview.promote_to == tmp_path / "downloads"
