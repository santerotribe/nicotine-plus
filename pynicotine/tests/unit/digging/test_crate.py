# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

from pynicotine.digging.crate import STATUS_KEPT, Crate, CrateTrack, slugify


def test_add_is_idempotent(tmp_path):

    crate = Crate(tmp_path / "crate.json")
    first = crate.add(CrateTrack(username="dj", virtual_path="Music/a.flac", filename="a.flac"))
    second = crate.add(CrateTrack(username="dj", virtual_path="Music/a.flac", filename="a.flac"))

    assert first.id == second.id
    assert len(crate) == 1


def test_status_filter_and_remove(tmp_path):

    crate = Crate(tmp_path / "crate.json")
    keep = crate.add(CrateTrack(username="dj", virtual_path="Music/a.flac", status=STATUS_KEPT))
    crate.add(CrateTrack(username="dj", virtual_path="Music/b.flac"))

    assert [track.id for track in crate.by_status(STATUS_KEPT)] == [keep.id]
    assert crate.remove(keep.id)
    assert len(crate) == 1


def test_save_and_reload(tmp_path):

    path = tmp_path / "crate.json"
    crate = Crate(path)
    track = crate.add(CrateTrack(username="dj", virtual_path="Music/a.flac", bpm=92.5))
    track.stems = {"vocals": "/tmp/vocals.wav"}
    crate.save()

    reloaded = Crate(path)
    restored = reloaded.get(track.id)

    assert restored is not None
    assert restored.bpm == 92.5
    assert restored.stems == {"vocals": "/tmp/vocals.wav"}


def test_slugify():

    assert slugify("A Tribe Called Quest - 1nce Again.mp3") == "a-tribe-called-quest-1nce-again"
    assert slugify("...") == "track"
