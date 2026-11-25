# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Audition sessions: which file a native player should open right now."""

import time

from types import SimpleNamespace

from pynicotine.digging.audition.peer import PARTIAL_PLAY_THRESHOLD
from pynicotine.engineapi.audition import AuditionRegistry, AuditionSession


def _session(virtual_path="House\\A\\track.mp3", **kwargs) -> AuditionSession:

    return AuditionSession(username="dj", virtual_path=virtual_path, size=9000, **kwargs)


def _candidate(url="https://example.test/preview.m4a", source="itunes"):

    return SimpleNamespace(
        artist="Ruggier",
        title="Long Ride",
        label="Ruggier - Long Ride",
        album="Long Ride",
        duration=215.0,
        score=0.87,
        source=source,
        preview_url=url if source == "itunes" else "",
        stream_url=url if source == "youtube" else "",
        store_url="",
        artwork="",
    )


class FakePeer:

    def __init__(self, partial_path="", finished_path="", bytes_done=0, size=9000,
                 status="downloading from peer", error=""):

        self.partial_path = partial_path
        self.finished_path = finished_path
        self.bytes = bytes_done
        self.size = size
        self.status_text = status
        self.error = error
        self.transfer = None


def test_local_share_wins_over_everything(tmp_path):

    local = tmp_path / "track.mp3"
    local.write_bytes(b"audio")
    session = _session(local_path=str(local))
    session.peer = FakePeer(partial_path=str(local), bytes_done=9000)
    session.catalogue = [_candidate()]

    assert session.source() == {"kind": "local", "path": str(local), "complete": True}


def test_catalogue_is_used_before_enough_peer_bytes_exist():

    session = _session()
    session.peer = FakePeer(partial_path="/tmp/INCOMPLETE track.mp3", bytes_done=1024)
    session.catalogue = [_candidate()]

    source = session.source()

    assert source["kind"] == "catalogue"
    assert source["url"] == "https://example.test/preview.m4a"


def test_peer_file_replaces_the_catalogue_once_playable():

    session = _session()
    session.peer = FakePeer(partial_path="/tmp/INCOMPLETE track.mp3",
                            bytes_done=PARTIAL_PLAY_THRESHOLD)
    session.catalogue = [_candidate()]

    source = session.source()

    assert source["kind"] == "peer"
    assert source["path"] == "/tmp/INCOMPLETE track.mp3"
    assert source["complete"] is False
    assert source["bytes"] == PARTIAL_PLAY_THRESHOLD


def test_finished_peer_file_is_the_real_thing():

    session = _session()
    session.peer = FakePeer(partial_path="/tmp/track.mp3", finished_path="/tmp/track.mp3",
                            bytes_done=9000)

    source = session.source()

    assert source["kind"] == "peer"
    assert source["complete"] is True


def test_no_source_when_nothing_is_available_yet():

    session = _session()
    session.peer = FakePeer()

    assert session.source() is None


def test_youtube_stream_url_is_used_when_there_is_no_preview():

    session = _session()
    session.catalogue = [_candidate(url="https://stream.test/audio.webm", source="youtube")]

    assert session.source()["url"] == "https://stream.test/audio.webm"


def test_state_exposes_peer_progress_and_catalogue_shape():

    session = _session(duration_hint=215.0)
    session.peer = FakePeer(partial_path="/tmp/INCOMPLETE track.mp3", bytes_done=4500)
    session.catalogue = [_candidate()]
    session.catalogue_state = "matched"

    payload = session.state()

    assert payload["id"] == session.id
    assert payload["filename"] == "track.mp3"
    assert payload["folder"] == "House\\A"
    assert payload["duration"] == 215.0
    assert payload["peer"]["percent"] == 50.0
    assert payload["peer"]["partial_path"] == "/tmp/INCOMPLETE track.mp3"
    assert payload["catalogue"][0]["label"] == "Ruggier - Long Ride"
    assert payload["catalogue"][0]["playback_url"] == "https://example.test/preview.m4a"
    assert payload["source"]["kind"] == "catalogue"


def test_summary_is_cheap_and_names_the_file():

    session = _session()
    session.peer = FakePeer(bytes_done=900)

    summary = session.summary()

    assert summary["filename"] == "track.mp3"
    assert summary["percent"] == 10.0
    assert "catalogue" not in summary


def test_keep_records_a_crate_track(monkeypatch):

    recorded = {}

    def fake_keep(core, source, settings, peer=None):
        recorded["source"] = source
        recorded["peer"] = peer
        return SimpleNamespace(id="track-1", username=source.username,
                               filename=source.filename, virtual_path=source.virtual_path,
                               status="kept", bpm=None, local_path="", stems={},
                               als_path="", error="", added=time.time())

    def fake_source(**kwargs):
        kwargs["virtual_path"] = f"{kwargs['folder_path']}\\{kwargs['filename']}"
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr("pynicotine.digging.actions.keep_source", fake_keep)
    monkeypatch.setattr("pynicotine.digging.actions.TrackSource", fake_source)

    session = _session()
    session.peer = FakePeer()

    track = session.keep()

    assert track["id"] == "track-1"
    assert session.kept is True
    assert session.track_id == "track-1"
    assert recorded["source"].filename == "track.mp3"
    assert recorded["peer"] is session.peer


def test_registry_closes_and_reaps_idle_sessions():

    registry = AuditionRegistry()
    session = _session()
    registry._sessions[session.id] = session

    assert registry.summaries()[0]["id"] == session.id

    session.touched_at = time.time() - 10_000
    registry.reap()

    assert registry.summaries() == []
    assert registry.close(session.id) is False


def test_preview_sweep_is_throttled(monkeypatch):
    """A native client never opens the Dig window, so closing auditions sweeps."""

    from pynicotine.engineapi import audition

    calls = []

    class FakeEvents:

        @staticmethod
        def invoke_main_thread(callback):
            calls.append(callback)

    monkeypatch.setattr(audition, "events", FakeEvents)
    monkeypatch.setattr(audition, "_LAST_SWEEP", 0.0)

    audition._schedule_sweep()
    audition._schedule_sweep()

    assert len(calls) == 1


def test_close_is_idempotent():

    session = _session()
    session.close()
    session.close()

    assert session.closed is True
