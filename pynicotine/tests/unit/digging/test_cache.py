# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import time

from pynicotine.digging.cache import PreviewCache


def _make(path, size=1024, age=0.0):

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))
    return path


def test_usage_counts_bytes(tmp_path):

    _make(tmp_path / "a.wav", 2048)
    _make(tmp_path / "sub" / "b.wav", 1024)

    report = PreviewCache(tmp_path).usage()

    assert report.files == 2
    assert report.total_bytes == 3072


def test_enforce_evicts_oldest_first(tmp_path):

    _make(tmp_path / "old.wav", 1024, age=300)
    _make(tmp_path / "new.wav", 1024, age=10)

    cache = PreviewCache(tmp_path, max_bytes=1024)
    report = cache.enforce()

    assert report.removed == 1
    assert not (tmp_path / "old.wav").exists()
    assert (tmp_path / "new.wav").exists()


def test_enforce_noop_when_under_limit(tmp_path):

    _make(tmp_path / "a.wav", 512)
    report = PreviewCache(tmp_path, max_bytes=1024 * 1024).enforce()

    assert report.removed == 0
    assert (tmp_path / "a.wav").exists()


def test_clear_removes_everything(tmp_path):

    _make(tmp_path / "a.wav", 512)
    _make(tmp_path / "deep" / "b.wav", 512)

    report = PreviewCache(tmp_path).clear()

    assert report.removed == 2
    assert not list(tmp_path.rglob("*.wav"))
