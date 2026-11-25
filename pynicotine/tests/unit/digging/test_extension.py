# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

from pynicotine.digging.audition.player import should_extend


RATE = 44100


def test_does_not_extend_immediately_after_load():

    assert not should_extend(position=60.0, duration=200.0, decoded=60.5, frames=RATE * 3,
                             sample_rate=RATE, seconds_since_load=0.4, buffer_done=False)


def test_extends_at_the_edge_with_data():

    assert should_extend(position=60.0, duration=200.0, decoded=60.5, frames=RATE * 3,
                         sample_rate=RATE, seconds_since_load=4.0, buffer_done=False)


def test_does_not_extend_without_decoded_audio():

    assert not should_extend(position=60.0, duration=200.0, decoded=60.0, frames=0,
                             sample_rate=RATE, seconds_since_load=5.0, buffer_done=False)


def test_does_not_extend_a_finished_buffer():

    assert not should_extend(position=199.0, duration=200.0, decoded=200.0, frames=RATE * 200,
                             sample_rate=RATE, seconds_since_load=5.0, buffer_done=True)


def test_does_not_extend_away_from_the_edge():

    assert not should_extend(position=10.0, duration=200.0, decoded=60.0, frames=RATE * 60,
                             sample_rate=RATE, seconds_since_load=5.0, buffer_done=False)
