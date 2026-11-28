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


def test_crate_kinds_and_move(tmp_path):

    crate = Crate(tmp_path / "crate.json")
    sample = crate.add(CrateTrack(username="dj", virtual_path="Music/a.flac"))
    dj = crate.add(CrateTrack(username="dj", virtual_path="Music/b.flac", kind="dj"))

    assert [track.id for track in crate.by_kind("sample")] == [sample.id]
    assert [track.id for track in crate.by_kind("dj")] == [dj.id]

    moved = crate.set_kind(sample.id, "dj")

    assert moved is not None
    assert moved.kind == "dj"
    assert crate.by_kind("sample") == []
    assert {track.id for track in crate.by_kind("dj")} == {sample.id, dj.id}


def test_crate_kind_is_validated(tmp_path):

    crate = Crate(tmp_path / "crate.json")
    track = crate.add(CrateTrack(username="dj", virtual_path="Music/a.flac"))

    try:
        crate.set_kind(track.id, "mixtape")
    except ValueError as error:
        assert "unknown crate kind" in str(error)
    else:
        raise AssertionError("an unknown kind must be rejected")

    assert crate.set_kind("missing", "dj") is None


def test_add_reloads_before_writing(tmp_path):

    path = tmp_path / "crate.json"

    first = Crate(path)
    first.add(CrateTrack(username="u", virtual_path="a"))

    second = Crate(path)
    second.add(CrateTrack(username="u", virtual_path="b"))

    # The first instance is stale; its add must not drop the second's track.
    first.add(CrateTrack(username="u", virtual_path="c"))

    assert {track.virtual_path for track in Crate(path)} == {"a", "b", "c"}


def test_second_kind_moves_the_track(tmp_path):

    crate = Crate(tmp_path / "crate.json")
    track = crate.add(CrateTrack(username="u", virtual_path="a", kind="sample"))

    again = crate.add(CrateTrack(username="u", virtual_path="a", kind="dj"))

    assert again.id == track.id
    assert again.kind == "dj"
    assert Crate(crate.path).get(track.id).kind == "dj"


def test_update_keeps_concurrent_entries(tmp_path):

    path = tmp_path / "crate.json"

    writer = Crate(path)
    track = writer.add(CrateTrack(username="u", virtual_path="a"))

    other = Crate(path)
    other.add(CrateTrack(username="u", virtual_path="b"))

    writer.update(track.id, status="ready")

    assert {entry.virtual_path for entry in Crate(path)} == {"a", "b"}
    assert Crate(path).get(track.id).status == "ready"
