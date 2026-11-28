# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Audition sessions: the peer's real file, plus a catalogue stand-in.

The GTK Dig window owns its own audio output. A native front end owns its own
(AVAudioEngine), so what it needs from the engine is not playback but *state*:
which file to open right now, how many bytes of it exist, whether the peer is
still queued, and what the catalogue thinks the track is.

One session per auditioned file. It starts the peer preview download, resolves
catalogue matches in the background, publishes changes to `GET /events` and
answers `GET /audition/<id>` with a resolved source a native player can open.
Nothing here plays audio; the PortAudio player is untouched.
"""

from __future__ import annotations

import threading
import time
import uuid

from pathlib import Path

from pynicotine.digging.audition.peer import PARTIAL_PLAY_THRESHOLD
from pynicotine.engineapi.hub import event_hub
from pynicotine.events import events
from pynicotine.logfacility import log

IDLE_SECONDS = 30 * 60
PUBLISH_INTERVAL = 0.5
SWEEP_INTERVAL = 60.0

_LAST_SWEEP = 0.0


def _candidate_dict(candidate) -> dict:

    return {
        "artist": candidate.artist,
        "title": candidate.title,
        "label": candidate.label,
        "album": candidate.album,
        "duration": float(candidate.duration or 0.0),
        "score": round(float(candidate.score or 0.0), 3),
        "source": candidate.source,
        "preview_url": candidate.preview_url,
        "stream_url": candidate.stream_url,
        "playback_url": candidate.preview_url or candidate.stream_url,
        "store_url": candidate.store_url,
        "artwork": candidate.artwork,
    }


class AuditionSession:

    def __init__(self, username: str, virtual_path: str, filename: str = "", size: int = 0,
                 attributes=None, duration_hint: float = 0.0, local_path: str = "") -> None:

        self.id = uuid.uuid4().hex[:12]
        self.username = username
        self.virtual_path = virtual_path
        self.folder = virtual_path.rpartition("\\")[0]
        self.filename = filename or virtual_path.rpartition("\\")[2] or virtual_path
        self.size = int(size or 0)
        self.attributes = attributes
        self.duration_hint = float(duration_hint or 0.0)
        self.local_path = local_path or ""

        self.created_at = time.time()
        self.touched_at = self.created_at
        self.closed = False
        self.kept = False
        self.track_id = ""

        self.peer = None
        self.peer_error = ""
        self.catalogue: list = []
        self.catalogue_state = "pending"
        self.catalogue_error = ""

        self._lock = threading.Lock()
        self._last_publish = 0.0

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        """Start the peer preview and catalogue lookups. Call on the engine thread."""

        self._start_peer()
        threading.Thread(target=self._catalogue_worker, daemon=True,
                         name=f"audition-catalogue-{self.id}").start()
        self._publish(force=True)

    def _start_peer(self) -> None:

        if self.local_path or not self.username or not self.virtual_path:
            # Our own shares are on disk: downloading them from ourselves would
            # queue a pointless transfer.
            return

        from pynicotine.digging.audition.peer import PeerPreview
        from pynicotine.digging.settings import DiggingSettings

        try:
            settings = DiggingSettings.load()
            settings.ensure_dirs()
            self.peer = PeerPreview(
                username=self.username,
                virtual_path=self.virtual_path,
                filename=self.filename,
                size=self.size,
                attributes=self.attributes,
                cache_dir=settings.work_path / "previews",
            )
            self.peer.start(on_update=self._on_peer_update, on_audio_ready=self._on_peer_audio)

        except Exception as error:  # noqa: BLE001 - catalogue playback must survive
            self.peer = None
            self.peer_error = str(error)
            log.add(f"Engine API: peer preview failed for {self.filename}: {error}")

    def close(self) -> None:

        if self.closed:
            return

        self.closed = True

        if self.peer is not None:
            try:
                self.peer.cancel()

            except Exception as error:  # noqa: BLE001
                log.add_debug(f"Engine API: could not cancel preview: {error}")

        event_hub().publish("audition_closed", id=self.id, username=self.username, filename=self.filename)

    def touch(self) -> None:

        self.touched_at = time.time()

    # -- catalogue --------------------------------------------------------

    def _catalogue_worker(self) -> None:

        from pynicotine.digging.audition import match

        try:
            fast = match.resolve(self.filename, expected_duration=self.duration_hint, sources=("itunes",))

            if fast and not self.closed:
                self._set_catalogue(fast)

            full = match.resolve(self.filename, expected_duration=self.duration_hint)

            if full and not self.closed and (not fast or full[0].score > fast[0].score + 0.05):
                self._set_catalogue(full)

        except Exception as error:  # noqa: BLE001 - a catalogue miss is not an error
            if not self.closed:
                self.catalogue_state = "error"
                self.catalogue_error = str(error)
                self._publish(force=True)
            return

        if self.closed or not self.catalogue:
            return

        best = self.catalogue[0]

        if best.source == "youtube" and not best.stream_url:
            try:
                best.stream_url = match.youtube_stream(best)
                self._publish(force=True)

            except Exception as error:  # noqa: BLE001
                log.add_debug(f"Engine API: could not resolve youtube stream: {error}")

    def _set_catalogue(self, candidates) -> None:

        with self._lock:
            self.catalogue = candidates[:5]
            self.catalogue_state = "matched"

        self._publish(force=True)

    # -- peer callbacks ---------------------------------------------------

    def _on_peer_update(self, preview) -> None:

        if self.closed:
            return

        terminal = bool(preview.finished_path or preview.error)
        self._publish(force=terminal)

    def _on_peer_audio(self, _preview) -> None:

        if not self.closed:
            self._publish(force=True)

    def _publish(self, force: bool = False) -> None:

        if self.closed:
            return

        now = time.monotonic()

        if not force and (now - self._last_publish) < PUBLISH_INTERVAL:
            return

        self._last_publish = now
        event_hub().publish("audition", **self.state())

    # -- state ------------------------------------------------------------

    def _peer_block(self) -> dict:

        preview = self.peer
        transfer = getattr(preview, "transfer", None) if preview is not None else None

        if preview is None:
            return {
                "active": False,
                "status": "local file" if self.local_path else "not started",
                "bytes": 0,
                "size": self.size,
                "percent": 0.0,
                "queue_position": 0,
                "partial_path": "",
                "finished_path": "",
                "complete": False,
                "error": self.peer_error,
            }

        bytes_done = int(getattr(preview, "bytes", 0) or 0)
        total = int(getattr(preview, "size", 0) or self.size or 0)

        return {
            "active": not self.closed,
            "status": preview.status_text,
            "bytes": bytes_done,
            "size": total,
            "percent": round((bytes_done / total) * 100, 1) if total else 0.0,
            "queue_position": int(getattr(transfer, "queue_position", 0) or 0),
            "partial_path": preview.partial_path,
            "finished_path": preview.finished_path,
            "complete": bool(preview.finished_path),
            "error": preview.error or self.peer_error,
        }

    def source(self) -> dict | None:
        """What a native player should open, most real first."""

        if self.local_path and Path(self.local_path).is_file():
            return {"kind": "local", "path": self.local_path, "complete": True}

        peer = self._peer_block()

        if peer["finished_path"]:
            return {"kind": "peer", "path": peer["finished_path"], "bytes": peer["bytes"],
                    "total": peer["size"], "complete": True}

        has_audio = bool(peer["partial_path"]) and peer["bytes"] >= PARTIAL_PLAY_THRESHOLD
        catalogue_url = ""

        for candidate in self.catalogue:
            catalogue_url = candidate.preview_url or candidate.stream_url

            if catalogue_url:
                break

        if has_audio:
            return {"kind": "peer", "path": peer["partial_path"], "bytes": peer["bytes"],
                    "total": peer["size"], "complete": False}

        if catalogue_url:
            return {"kind": "catalogue", "url": catalogue_url, "bytes": 0,
                    "total": 0, "complete": False}

        if peer["partial_path"]:
            return {"kind": "peer", "path": peer["partial_path"], "bytes": peer["bytes"],
                    "total": peer["size"], "complete": False}

        return None

    def state(self) -> dict:

        return {
            "id": self.id,
            "username": self.username,
            "virtual_path": self.virtual_path,
            "folder": self.folder,
            "filename": self.filename,
            "size": self.size,
            "duration": self.duration_hint,
            "local_path": self.local_path,
            "kept": self.kept,
            "track_id": self.track_id,
            "created_at": int(self.created_at),
            "catalogue_state": self.catalogue_state,
            "catalogue_error": self.catalogue_error,
            "catalogue": [_candidate_dict(candidate) for candidate in self.catalogue],
            "peer": self._peer_block(),
            "source": self.source(),
        }

    def summary(self) -> dict:

        peer = self._peer_block()

        return {
            "id": self.id,
            "username": self.username,
            "filename": self.filename,
            "virtual_path": self.virtual_path,
            "size": self.size,
            "kept": self.kept,
            "peer_status": peer["status"],
            "percent": peer["percent"],
            "catalogue_state": self.catalogue_state,
            "created_at": int(self.created_at),
        }

    # -- keeping ----------------------------------------------------------

    def keep(self, kind: str = "sample") -> dict:
        """Keep the file: crate entry now, download promoted when it finishes."""

        from pynicotine.core import core
        from pynicotine.digging.actions import TrackSource, keep_source
        from pynicotine.digging.settings import DiggingSettings
        from pynicotine.engineapi.serialize import crate_track_dict

        settings = DiggingSettings.load()
        track = keep_source(
            core,
            TrackSource(
                username=self.username,
                folder_path=self.folder,
                filename=self.filename,
                size=self.size,
                attributes=self.attributes,
            ),
            settings,
            peer=self.peer,
            kind=kind,
        )

        self.kept = True
        self.track_id = track.id
        self._publish(force=True)
        return crate_track_dict(track)


class AuditionRegistry:

    def __init__(self) -> None:

        self._sessions: dict[str, AuditionSession] = {}
        self._lock = threading.Lock()

    def start(self, username: str, virtual_path: str, filename: str = "", size: int = 0,
              attributes=None, duration_hint: float = 0.0, local_path: str = "") -> AuditionSession:

        self.reap()

        session = AuditionSession(
            username=username,
            virtual_path=virtual_path,
            filename=filename,
            size=size,
            attributes=attributes,
            duration_hint=duration_hint,
            local_path=local_path,
        )

        with self._lock:
            self._sessions[session.id] = session

        session.start()
        return session

    def get(self, session_id: str) -> AuditionSession | None:

        session = self._sessions.get(session_id)

        if session is not None:
            session.touch()

        return session

    def close(self, session_id: str) -> bool:

        with self._lock:
            session = self._sessions.pop(session_id, None)

        if session is None:
            return False

        session.close()

        # A native client never opens the Dig window, so nothing else runs the
        # preview sweep. Do it here, throttled, on the engine thread.
        _schedule_sweep()
        return True

    def summaries(self) -> list[dict]:

        self.reap()

        with self._lock:
            sessions = list(self._sessions.values())

        return [session.summary() for session in sessions]

    def reap(self) -> None:

        cutoff = time.time() - IDLE_SECONDS

        with self._lock:
            stale = [sid for sid, session in self._sessions.items() if session.touched_at < cutoff]

        for session_id in stale:
            log.add_debug(f"Engine API: closing idle audition {session_id}")
            self.close(session_id)


def _schedule_sweep() -> None:
    """Trim abandoned previews, at most once a minute, on the engine thread."""

    global _LAST_SWEEP

    now = time.monotonic()

    if (now - _LAST_SWEEP) < SWEEP_INTERVAL:
        return

    _LAST_SWEEP = now
    events.invoke_main_thread(_run_sweep)


def _run_sweep() -> None:

    from pynicotine.core import core
    from pynicotine.digging.maintenance import sweep

    try:
        report = sweep(core=core)

    except Exception as error:  # noqa: BLE001 - housekeeping is best effort
        log.add_debug(f"Engine API: preview sweep failed: {error}")
        return

    if report.transfers_removed or report.files_removed:
        log.add(f"Digging: cleaned up {report.transfers_removed} preview transfers, "
                f"{report.files_removed} files ({report.bytes_freed / (1024 * 1024):.1f} MB)")


SESSIONS = AuditionRegistry()


def audition_sessions() -> AuditionRegistry:
    return SESSIONS
