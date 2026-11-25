# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Push channel for the engine API: Server-Sent Events.

A native front end should never poll. The engine already emits events for every
state change it cares about (login, browse, transfers, searches, pipeline); this
module funnels those into one ordered stream that any number of clients can
subscribe to over `GET /events`.

Two rules keep the engine safe:

* publishing never blocks, never runs front-end code and never raises - a slow or
  dead subscriber only loses events, it cannot stall a browse or a transfer;
* work that must happen on the engine thread is scheduled with
  `events.schedule` (browse settlement) or done in the callback itself.

Transfer progress arrives many times per second per file, so updates are
coalesced and flushed at a fixed rate by a small daemon thread. Search results
arrive one message per peer, which is already a sensible batch size.
"""

from __future__ import annotations

import queue
import threading
import time

from pynicotine.events import events
from pynicotine.logfacility import log

SUBSCRIBER_QUEUE_SIZE = 2048
TRANSFER_FLUSH_SECONDS = 0.4
TRANSFERS_PER_EVENT = 200
BROWSE_SETTLE_SECONDS = 1
CRATE_SNAPSHOT_LIMIT = 2000


def guard(callback):
    """Wrap an engine listener so the API can never take the client down.

    events.emit() treats an exception in a listener as fatal and quits the
    client, which is right for the engine and wrong for an optional side
    channel like this one.
    """

    def guarded(*args, **kwargs):

        try:
            return callback(*args, **kwargs)

        except Exception as error:  # noqa: BLE001 - never fatal
            log.add_debug(f"Engine events: {getattr(callback, '__name__', callback)} failed: {error}")
            return None

    return guarded


class Subscriber:
    """One connected client. Bounded, so a stalled reader cannot grow memory."""

    __slots__ = ("queue", "types", "excluded", "dropped", "closed", "created")

    def __init__(self, types: set[str] | None = None, excluded: set[str] | None = None) -> None:

        self.queue: queue.Queue = queue.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self.types = types
        self.excluded = excluded or set()
        self.dropped = 0
        self.closed = False
        self.created = time.time()

    def wants(self, event_type: str) -> bool:

        if self.excluded and event_type in self.excluded:
            return False

        if self.types is not None:
            # "hello" and "gap" are protocol events, always delivered
            return event_type in self.types or event_type in {"hello", "gap"}

        return True

    def offer(self, payload: dict) -> None:

        if self.closed:
            return

        try:
            self.queue.put_nowait(payload)
            return

        except queue.Full:
            pass

        # Drop the oldest event: live state matters more than history, and the
        # client can always re-read a paged endpoint for what it missed.
        try:
            self.queue.get_nowait()
            self.queue.put_nowait(payload)

        except (queue.Empty, queue.Full):
            pass

        self.dropped += 1

    def take_dropped(self) -> int:

        dropped = self.dropped
        self.dropped = 0
        return dropped


class EventHub:

    def __init__(self) -> None:

        self._subscribers: list[Subscriber] = []
        self._lock = threading.Lock()
        self._seq = 0
        self._started = False
        self._flusher: threading.Thread | None = None
        self._pending_transfers: dict[str, dict] = {}
        self._browse_generation: dict[str, int] = {}
        self._last_event_at = 0.0

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:

        if self._started:
            return

        for event_name, callback in (
            ("abort-download", self._on_transfer),
            ("clear-download", self._on_transfer),
            ("digging-status", self._on_digging_status),
            ("file-search-response", self._on_file_search_response),
            ("remove-search", self._on_search_removed),
            ("search-failed", self._on_search_failed),
            ("server-disconnect", self._on_server_disconnect),
            ("server-login", self._on_server_login),
            ("shared-file-list-failed", self._on_browse_failed),
            ("shared-file-list-response", self._on_browse_response),
            ("update-download", self._on_transfer),
            ("user-browse-show-user", self._on_browse_started),
        ):
            events.connect(event_name, guard(callback))

        self._started = True

        if self._flusher is None:
            self._flusher = threading.Thread(target=self._flush_loop, name="engine-events", daemon=True)
            self._flusher.start()

    # -- subscriptions ----------------------------------------------------

    def subscribe(self, types: set[str] | None = None,
                  excluded: set[str] | None = None) -> Subscriber:

        subscriber = Subscriber(types=types, excluded=excluded)

        with self._lock:
            self._subscribers.append(subscriber)

        self.start()
        return subscriber

    def unsubscribe(self, subscriber: Subscriber) -> None:

        subscriber.closed = True

        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

    @property
    def subscriber_count(self) -> int:

        with self._lock:
            return len(self._subscribers)

    # -- publishing -------------------------------------------------------

    def publish(self, event_type: str, **fields) -> None:

        try:
            self._publish(event_type, fields)

        except Exception as error:  # noqa: BLE001 - the stream is best effort
            log.add_debug(f"Engine events: could not publish {event_type}: {error}")

    def _publish(self, event_type: str, fields: dict) -> None:

        with self._lock:
            subscribers = list(self._subscribers)

            if not subscribers:
                return

            self._seq += 1
            payload = {"type": event_type, "seq": self._seq, "time": int(time.time())}
            payload.update(fields)

        self._last_event_at = time.time()

        for subscriber in subscribers:
            if subscriber.wants(event_type):
                subscriber.offer(payload)

    def snapshot(self) -> dict:
        """Current engine state, sent as the first event of every connection."""

        from pynicotine.core import core

        state = {
            "logged_in": bool(core.users.login_status),
            "username": core.users.login_username,
            "status": str(core.users.login_status),
            "privileges_seconds": core.users.privileges_left,
            "browsed_users": list(core.userbrowse.users),
        }

        try:
            transfers = [
                _transfer_payload(transfer)
                for transfer in list(core.downloads.transfers.values())[:TRANSFERS_PER_EVENT]
            ]

        except Exception:  # noqa: BLE001
            transfers = []

        return {
            "state": state,
            "transfers": transfers,
            "searches": _search_snapshot(),
            "auditions": _audition_snapshot(),
            "crate": _crate_snapshot(),
        }

    # -- engine events ----------------------------------------------------

    def _on_server_login(self, msg) -> None:

        from pynicotine.core import core

        self.publish(
            "login",
            username=core.users.login_username,
            success=bool(getattr(msg, "success", False)),
            reason=getattr(msg, "reason", "") or "",
            privileges_seconds=_privileges(),
        )

    def _on_server_disconnect(self, msg=None) -> None:

        self.publish(
            "disconnect",
            manual=bool(getattr(msg, "manual_disconnect", False)),
            relogged=bool(getattr(msg, "relogged", False)),
            username=None,
        )

    def _on_browse_started(self, username: str, path=None, new_request: bool = False,
                           switch_page: bool = True) -> None:

        del path, switch_page

        if not new_request:
            return

        self._browse_generation[username] = self._browse_generation.get(username, 0) + 1
        self.publish("browse_started", username=username)

    def _on_browse_response(self, msg) -> None:

        username = getattr(msg, "username", "")

        if not username:
            return

        generation = self._browse_generation.get(username, 0) + 1
        self._browse_generation[username] = generation

        self.publish("browse", done=False, **_browse_payload(username))

        # A share list can arrive as several messages; the browse is settled
        # once the peer stops sending. The scheduled check compares generations
        # so only the last message schedules a completion event.
        events.schedule(BROWSE_SETTLE_SECONDS, self._browse_settled, (username, generation))

    def _browse_settled(self, username: str, generation: int) -> None:

        if self._browse_generation.get(username) != generation:
            return

        self.publish("browse", done=True, **_browse_payload(username))

    def _on_browse_failed(self, username: str, is_offline: bool = False, disk_error=None) -> None:

        self.publish(
            "browse_failed",
            username=username,
            offline=bool(is_offline),
            error=str(disk_error) if disk_error else "",
        )

    def _on_transfer(self, transfer, *_args) -> None:
        # abort-download carries (transfer, status, update_parent); the others
        # carry (transfer, update_parent). Ignore the extras.

        if transfer is None:
            return

        key = f"{transfer.username}/{transfer.virtual_path}"

        with self._lock:
            self._pending_transfers[key] = _transfer_payload(transfer)

    def flush_transfers(self) -> None:
        """Coalesce queued transfer progress into one event."""

        with self._lock:
            if not self._pending_transfers:
                return

            keys = list(self._pending_transfers)[:TRANSFERS_PER_EVENT]
            batch = [self._pending_transfers.pop(key) for key in keys]

        self.publish("transfers", transfers=batch)

    def _flush_loop(self) -> None:

        while True:
            time.sleep(TRANSFER_FLUSH_SECONDS)
            self.flush_transfers()

    def _on_digging_status(self, track_id: str, **fields) -> None:

        payload = {"track_id": track_id}
        payload.update(fields)
        self.publish("crate", **payload)

    def _on_file_search_response(self, msg) -> None:

        from pynicotine.engineapi import searchstore

        event = searchstore.store().record(msg)

        if event is not None:
            self.publish("search", **event)

    def _on_search_failed(self, token: int, is_offline: bool = False) -> None:

        self.publish("search_failed", token=token, offline=bool(is_offline))

    def _on_search_removed(self, token: int) -> None:

        self.publish("search_removed", token=token)


# -- payload helpers ------------------------------------------------------

def _privileges() -> int | None:

    from pynicotine.core import core

    try:
        return core.users.privileges_left

    except Exception:  # noqa: BLE001
        return None


def _browse_payload(username: str) -> dict:

    from pynicotine.core import core

    summary = core.userbrowse.user_summary(username) or {}

    return {
        "username": username,
        "folders": summary.get("folders", 0),
        "files": summary.get("files", 0),
        "shared_size": summary.get("shared_size", 0),
        "messages": summary.get("messages", 0),
    }


def _transfer_payload(transfer) -> dict:

    from pynicotine.engineapi.serialize import transfer_dict

    return transfer_dict(transfer)


def _search_snapshot() -> list[dict]:

    from pynicotine.engineapi import searchstore

    return searchstore.store().summaries()


def _audition_snapshot() -> list[dict]:

    from pynicotine.engineapi.audition import audition_sessions

    return audition_sessions().summaries()


def _crate_snapshot() -> dict:

    try:
        from pynicotine.digging.actions import crate_for

        crate = crate_for()
        statuses: dict[str, int] = {}

        for track in crate.tracks[:CRATE_SNAPSHOT_LIMIT]:
            statuses[track.status] = statuses.get(track.status, 0) + 1

        return {"total": len(crate), "statuses": statuses}

    except Exception:  # noqa: BLE001 - the crate is optional
        return {"total": 0, "statuses": {}}


HUB = EventHub()


def event_hub() -> EventHub:
    return HUB


def type_filter(value: str) -> tuple[set[str] | None, set[str]]:
    """Parse ?types=a,b or ?types=-a,-b into an allow/deny pair."""

    names = {name.strip() for name in (value or "").split(",") if name.strip()}

    if not names:
        return None, set()

    excluded = {name[1:] for name in names if name.startswith("-")}

    if excluded:
        return None, excluded

    return names, set()
