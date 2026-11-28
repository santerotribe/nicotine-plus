# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Paged browse + JSON shapes used by any front end."""

from pynicotine.engineapi.serialize import file_dict, transfer_dict
from pynicotine.slskmessages import FileAttributes, SharedFile
from pynicotine.userbrowse import BrowsedUser, UserBrowse


def _file(name, size=1000, bitrate=320, length=200):

    return SharedFile(
        code=1,
        path=name,
        size=size,
        extension=None,
        attributes=FileAttributes(bitrate=bitrate, length=length, vbr=0,
                                  sample_rate=44100, bit_depth=16),
    )


def _browse(folder_files):

    browse = object.__new__(UserBrowse)
    browse.users = {}
    browse._browse_timing = {}

    user = BrowsedUser(username="dj")
    user.public_folders = folder_files
    user.num_folders = len(folder_files)
    user.num_files = sum(len(files) for files in folder_files.values())
    user.shared_size = sum(file.size for files in folder_files.values() for file in files)
    browse.users["dj"] = user
    return browse


def test_file_page_pages_without_copying_everything():

    files = [_file(f"track-{index:04d}.mp3") for index in range(1200)]
    browse = _browse({"Music": files})

    page = browse.file_page("dj", "Music", offset=1000, limit=100)

    assert page["total"] == 1200
    assert len(page["files"]) == 100
    assert page["files"][0].path == "track-1000.mp3"
    assert page["offset"] == 1000


def test_file_page_handles_unknown_folder_and_user():

    browse = _browse({"Music": [_file("a.mp3")]})

    assert browse.file_page("nobody", "Music") is None
    assert browse.file_page("dj", "Missing")["total"] == 0


def test_folder_page_reports_counts():

    browse = _browse({
        "A": [_file("1.mp3"), _file("2.mp3")],
        "B": [_file("3.mp3")],
    })

    page = browse.folder_page("dj", offset=1, limit=1)

    assert page["total"] == 2
    assert page["folders"][0]["name"] == "B"
    assert page["folders"][0]["files"] == 1
    assert page["folders"][0]["formats"] == {"mp3": 1}
    assert page["folders"][0]["duration"] == 200


def test_user_summary_is_cheap():

    browse = _browse({"A": [_file("1.mp3", size=5000)]})
    summary = browse.user_summary("dj")

    assert summary["folders"] == 1
    assert summary["files"] == 1
    assert summary["shared_size"] == 5000


def test_file_dict_is_raw_and_complete():

    payload = file_dict(_file("x.mp3", size=2048, bitrate=256, length=180))

    assert payload == {
        "name": "x.mp3",
        "size": 2048,
        "bitrate": 256,
        "length": 180,
        "vbr": 0,
        "sample_rate": 44100,
        "bit_depth": 16,
    }


def test_transfer_dict_percent_and_basename():

    class Transfer:
        username = "dj"
        virtual_path = "Music\\Sub\\track.mp3"
        folder_path = "/tmp"
        size = 1000
        current_byte_offset = 250
        status = "Transferring"
        queue_position = 0
        speed = 1024

    payload = transfer_dict(Transfer())

    assert payload["filename"] == "track.mp3"
    assert payload["percent"] == 25.0
