# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from pynicotine.digging.audition.match import (
    Candidate,
    parse_filename,
    score_candidate,
    similarity,
)


@pytest.mark.parametrize("filename,artist,title", [
    ("Max Dean, Luke Dean, Nafe Smallz - Not A Problem [Interscope Records].wav",
     "Max Dean, Luke Dean, Nafe Smallz", "Not A Problem"),
    ("01 Ruggier - Long Ride (Original Mix).aiff", "Ruggier", "Long Ride"),
    ("02 Ixer (UK) - Comin For Ya (Original Mix).aiff", "Ixer", "Comin For Ya"),
    ("04 - Some Random Bootleg Edit [320].mp3", "", "Some Random Bootleg Edit"),
    ("Track_01__Artist_Name_-_Song_Title.flac", "Artist Name", "Song Title"),
])
def test_parse_filename(filename, artist, title):

    parsed = parse_filename(filename)

    assert parsed.artist == artist
    assert parsed.title == title


def test_similarity_ignores_brackets_and_case():

    assert similarity("Not A Problem", "not a problem (feat. X)") > 0.5
    assert similarity("Long Ride", "Long Ride") == 1.0
    assert similarity("Apples", "Oranges") == 0.0


def test_duration_bonus_and_penalty():

    parsed = parse_filename("Ruggier - Long Ride (Original Mix).aiff")
    exact = Candidate(artist="Ruggier", title="Long Ride", album="", duration=360.0,
                      preview_url="x", artwork="", store_url="")
    wrong = Candidate(artist="Ruggier", title="Long Ride", album="", duration=100.0,
                      preview_url="x", artwork="", store_url="")

    close = score_candidate(exact, parsed, expected_duration=361.0)
    far = score_candidate(wrong, parsed, expected_duration=361.0)

    assert close > far
    assert 0.0 <= far <= 1.0
