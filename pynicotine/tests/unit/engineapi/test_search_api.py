# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Engine-side search results: grouping, paging, filtering and caps."""

from pynicotine.engineapi import searchstore
from pynicotine.engineapi.searchstore import SearchStore
from pynicotine.slskmessages import FileAttributes, SharedFile


def _file(path, size=1000, bitrate=320, length=200):

    return SharedFile(
        code=1,
        path=path,
        size=size,
        extension=None,
        attributes=FileAttributes(bitrate=bitrate, length=length, vbr=0,
                                  sample_rate=44100, bit_depth=16),
    )


class FakeResponse:

    def __init__(self, token, public=(), private=(), username="dj", slot_available=True,
                 upload_speed=1000, queued=0):

        self.token = token
        self.username = username
        self.public_files = list(public)
        self.private_files = list(private)
        self.slot_available = slot_available
        self.upload_speed = upload_speed
        self.num_queued_uploads = queued
        self.is_rejected = False


def _store(*entries) -> SearchStore:

    store = SearchStore()

    for token, term in entries:
        store.create(token, term, "global")

    return store


def test_results_are_grouped_by_user_and_folder():

    store = _store((1, "ruggier"))
    event = store.record(FakeResponse(1, public=[
        _file("House\\Deep\\a.mp3"),
        _file("House\\Deep\\b.mp3"),
        _file("House\\Classic\\c.mp3"),
    ]))

    assert event == {"token": 1, "term": "ruggier", "user": "dj", "added": 3, "total": 3}

    summary = store.get(1).summary()
    assert summary["total"] == 3
    assert summary["users"] == 1

    users = store.users_page(1)
    assert users["users"][0]["username"] == "dj"
    assert users["users"][0]["files"] == 3
    assert users["users"][0]["folders"] == 2
    assert users["users"][0]["total_size"] == 3000


def test_results_page_is_stable_and_paged():

    store = _store((1, "term"))
    store.record(FakeResponse(1, public=[_file(f"F\\{index}.mp3") for index in range(1200)]))

    page = store.results_page(1, offset=1100, limit=100)

    assert page["total"] == 1200
    assert len(page["results"]) == 100
    assert page["results"][0]["virtual_path"] == "F\\1100.mp3"
    assert page["results"][0]["filename"] == "1100.mp3"
    assert page["results"][0]["folder"] == "F"
    assert page["results"][0]["bitrate"] == 320


def test_users_are_ordered_by_file_count():

    store = _store((1, "term"))
    store.record(FakeResponse(1, public=[_file("A\\1.mp3")], username="small"))
    store.record(FakeResponse(1, public=[_file(f"A\\{i}.mp3") for i in range(5)], username="big"))

    usernames = [user["username"] for user in store.users_page(1)["users"]]
    assert usernames == ["big", "small"]


def test_files_page_handles_folders_and_files():

    store = _store((1, "term"))
    store.record(FakeResponse(1, public=[_file("A\\1.mp3"), _file("B\\2.mp3")]))

    folders = store.files_page(1, "dj")
    assert folders["folders"] == {"A": 1, "B": 1}

    files = store.files_page(1, "dj", folder="A")
    assert files["total"] == 1
    assert files["files"][0]["filename"] == "1.mp3"

    assert store.files_page(1, "nobody")["total"] == 0


def test_filters_drop_unrelated_and_excluded_results():

    store = SearchStore()
    store.create(1, "ruggier long ride", "global",
                 included_words=["ruggier", "ride"], excluded_words=["instrumental"])

    event = store.record(FakeResponse(1, public=[
        _file("A\\Ruggier - Long Ride.mp3"),
        _file("A\\Ruggier - Long Ride (Instrumental).mp3"),
        _file("A\\Someone Else - Other.mp3"),
    ]))

    assert event["added"] == 1
    assert store.get(1).total == 1


def test_private_results_are_flagged():

    store = _store((1, "term"))
    store.record(FakeResponse(1, private=[_file("A\\private.mp3", size=42)]))

    result = store.results_page(1)["results"][0]
    assert result["private"] is True
    assert result["size"] == 42


def test_unknown_tokens_are_ignored():

    store = _store((1, "term"))

    assert store.record(FakeResponse(99, public=[_file("A\\1.mp3")])) is None
    assert store.results_page(99) is None
    assert store.users_page(99) is None
    assert store.files_page(99, "dj") is None


def test_result_cap_is_reported_not_hidden(monkeypatch):

    monkeypatch.setattr(searchstore, "MAX_RESULTS_PER_SEARCH", 2)
    store = _store((1, "term"))

    store.record(FakeResponse(1, public=[_file(f"A\\{index}.mp3") for index in range(5)]))

    entry = store.get(1)
    assert entry.total == 2
    assert entry.dropped == 3
    assert entry.summary()["dropped"] == 3


def test_tracked_searches_are_capped(monkeypatch):

    monkeypatch.setattr(searchstore, "MAX_TRACKED_SEARCHES", 2)
    store = SearchStore()
    store.create(1, "one", "global")
    store.create(2, "two", "global")
    store.create(3, "three", "global")

    assert store.get(1) is None
    assert store.get(3) is not None


def test_remove_forgets_the_result_set():

    store = _store((1, "term"))
    store.record(FakeResponse(1, public=[_file("A\\1.mp3")]))

    assert store.remove(1) is True
    assert store.get(1) is None
    assert store.remove(1) is False


def test_pages_clamp_negative_offsets_and_limits():

    store = _store((1, "term"))
    store.record(FakeResponse(1, public=[_file(f"A\\{index}.mp3") for index in range(3)]))

    page = store.results_page(1, offset=-5, limit=0)
    assert page["offset"] == 0
    assert page["limit"] == 1
    assert len(page["results"]) == 1


def test_remove_drops_every_page_of_a_search():

    store = _store((1, "term"), (2, "other"))
    store.record(FakeResponse(1, public=[_file("F\\a.mp3")]))
    store.record(FakeResponse(2, public=[_file("F\\b.mp3")]))

    assert store.remove(1) is True

    assert store.get(1) is None
    assert store.results_page(1) is None
    assert store.users_page(1) is None
    assert store.get(2).summary()["total"] == 1
    assert store.remove(1) is False
