# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

from pynicotine.digging.rolodex import Ledger


def test_add_dedupes_and_reloads(tmp_path):

    path = tmp_path / "rolodex.json"
    ledger = Ledger(path, "santero")
    ledger.add("dj", "Music\\a.flac", "Music", "a.flac", "sample")
    ledger.add("dj", "Music\\a.flac", "Music", "a.flac", "dj")

    entries = ledger.as_list()

    assert len(entries) == 1
    assert entries[0]["kind"] == "dj"

    reloaded = Ledger(path, "mara")

    assert reloaded.as_list()[0]["found_by"] == "santero"


def test_two_members_accumulate(tmp_path):

    path = tmp_path / "rolodex.json"

    Ledger(path, "santero").add("peerA", "A\\a.flac")
    Ledger(path, "mara").add("peerB", "B\\b.flac")

    entries = Ledger(path, "reader").as_list()

    assert {entry["peer"] for entry in entries} == {"peerA", "peerB"}
    assert {entry["found_by"] for entry in entries} == {"santero", "mara"}


def test_stars_are_per_member(tmp_path):

    path = tmp_path / "rolodex.json"

    Ledger(path, "santero").star("dj", True)
    Ledger(path, "mara").star("dj", True)

    assert len(Ledger(path, "reader").as_list()) == 2

    Ledger(path, "mara").star("dj", False)

    remaining = Ledger(path, "reader").as_list()

    assert len(remaining) == 1
    assert remaining[0]["found_by"] == "santero"
