# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Search results kept in the engine, not in a front end.

The GTK client builds a tree model per search tab. A native front end wants the
opposite: cheap paged reads and a push notification when more results arrive. So
searches started through the API are tracked here, in arrival order, grouped by
user and folder, and served through the same paging shape as user browse.

Only API searches are tracked: a search started in the GTK client keeps its
results in the GTK model and costs this module nothing.
"""

from __future__ import annotations

import threading
import time

from dataclasses import dataclass, field

from pynicotine.events import events
from pynicotine.logfacility import log

MAX_RESULTS_PER_SEARCH = 50000
MAX_TRACKED_SEARCHES = 32


@dataclass(slots=True)
class Result:

    username: str
    virtual_path: str
    folder: str
    filename: str
    size: int = 0
    bitrate: int | None = None
    length: int | None = None
    vbr: int | None = None
    sample_rate: int | None = None
    bit_depth: int | None = None
    slot_available: bool = True
    upload_speed: int = 0
    queue_position: int = 0
    private: bool = False

    def to_dict(self) -> dict:

        return {
            "username": self.username,
            "virtual_path": self.virtual_path,
            "folder": self.folder,
            "filename": self.filename,
            "size": self.size,
            "bitrate": self.bitrate,
            "length": self.length,
            "vbr": self.vbr,
            "sample_rate": self.sample_rate,
            "bit_depth": self.bit_depth,
            "slot_available": self.slot_available,
            "upload_speed": self.upload_speed,
            "queue_position": self.queue_position,
            "private": self.private,
        }


@dataclass(slots=True)
class UserBucket:

    username: str
    slot_available: bool = True
    upload_speed: int = 0
    queue_position: int = 0
    files: int = 0
    total_size: int = 0
    folders: dict[str, list[Result]] = field(default_factory=dict)

    def summary(self) -> dict:

        return {
            "username": self.username,
            "files": self.files,
            "folders": len(self.folders),
            "total_size": self.total_size,
            "slot_available": self.slot_available,
            "upload_speed": self.upload_speed,
            "queue_position": self.queue_position,
        }


class SearchEntry:

    __slots__ = ("token", "term", "mode", "created_at", "last_result_at", "dropped",
                 "included_words", "excluded_words", "users", "flat", "_sorted")

    def __init__(self, token: int, term: str, mode: str, included_words, excluded_words) -> None:

        self.token = token
        self.term = term
        self.mode = mode
        self.created_at = time.time()
        self.last_result_at = 0.0
        self.dropped = 0
        self.included_words = list(included_words or ())
        self.excluded_words = list(excluded_words or ())
        self.users: dict[str, UserBucket] = {}
        self.flat: list[Result] = []
        self._sorted: list[UserBucket] | None = None

    @property
    def total(self) -> int:
        return len(self.flat)

    def add(self, msg, username: str, records: list[Result]) -> int:

        bucket = self.users.get(username)

        if bucket is None:
            bucket = self.users[username] = UserBucket(
                username=username,
                slot_available=bool(getattr(msg, "slot_available", True)),
                upload_speed=int(getattr(msg, "upload_speed", 0) or 0),
                queue_position=int(getattr(msg, "num_queued_uploads", 0) or 0),
            )

        added = 0

        for record in records:
            if len(self.flat) >= MAX_RESULTS_PER_SEARCH:
                self.dropped += 1
                continue

            bucket.folders.setdefault(record.folder, []).append(record)
            bucket.files += 1
            bucket.total_size += record.size
            self.flat.append(record)
            added += 1

        if added:
            self.last_result_at = time.time()
            self._sorted = None

        return added

    def accepts(self, path: str) -> bool:

        lowered = path.lower()

        if self.excluded_words and any(word in lowered for word in self.excluded_words):
            return False

        if self.included_words and not all(word in lowered for word in self.included_words):
            return False

        return True

    @property
    def sorted_users(self) -> list[UserBucket]:

        if self._sorted is None:
            self._sorted = sorted(self.users.values(), key=lambda bucket: (-bucket.files, bucket.username.lower()))

        return self._sorted

    def summary(self) -> dict:

        return {
            "token": self.token,
            "term": self.term,
            "mode": self.mode,
            "total": self.total,
            "users": len(self.users),
            "dropped": self.dropped,
            "created_at": int(self.created_at),
            "last_result_at": int(self.last_result_at),
        }


class SearchStore:

    def __init__(self) -> None:

        self._entries: dict[int, SearchEntry] = {}
        self._lock = threading.Lock()
        self._started = False

    def start(self) -> None:

        if self._started:
            return

        from pynicotine.engineapi.hub import guard

        for event_name, callback in (
            ("remove-search", self._on_remove_search),
            ("server-disconnect", self._on_server_disconnect),
        ):
            events.connect(event_name, guard(callback))

        self._started = True

    # -- lifecycle --------------------------------------------------------

    def create(self, token: int, term: str, mode: str, included_words=None,
               excluded_words=None) -> SearchEntry:

        self.start()
        entry = SearchEntry(token, term, mode, included_words, excluded_words)

        with self._lock:
            while len(self._entries) >= MAX_TRACKED_SEARCHES:
                oldest = min(self._entries.values(), key=lambda item: item.created_at)
                del self._entries[oldest.token]

            self._entries[token] = entry

        return entry

    def get(self, token: int) -> SearchEntry | None:

        return self._entries.get(token)

    def remove(self, token: int) -> bool:

        with self._lock:
            return self._entries.pop(token, None) is not None

    def summaries(self) -> list[dict]:

        with self._lock:
            entries = sorted(self._entries.values(), key=lambda item: item.created_at)

        return [entry.summary() for entry in entries]

    # -- result intake ----------------------------------------------------

    def record(self, msg) -> dict | None:
        """Store one peer's results. Returns the event payload, if anything was added."""

        token = getattr(msg, "token", None)

        if token is None or token not in self._entries:
            return None

        if getattr(msg, "is_rejected", False):
            return None

        entry = self._entries[token]
        username = getattr(msg, "username", "") or getattr(msg, "search_username", "")

        if not username:
            return None

        try:
            from pynicotine.core import core

            if core.network_filter.is_user_ignored(username):
                return None

        except Exception:  # noqa: BLE001 - filtering is best effort
            pass

        records: list[Result] = []

        for is_private, files in ((False, msg.public_files), (True, msg.private_files)):
            for file_data in files or ():
                path = file_data.path

                if not entry.accepts(path):
                    continue

                folder, _separator, filename = path.rpartition("\\")
                attributes = file_data.attributes

                records.append(Result(
                    username=username,
                    virtual_path=path,
                    folder=folder,
                    filename=filename or path,
                    size=int(file_data.size or 0),
                    bitrate=getattr(attributes, "bitrate", None),
                    length=getattr(attributes, "length", None),
                    vbr=getattr(attributes, "vbr", None),
                    sample_rate=getattr(attributes, "sample_rate", None),
                    bit_depth=getattr(attributes, "bit_depth", None),
                    slot_available=bool(getattr(msg, "slot_available", True)),
                    upload_speed=int(getattr(msg, "upload_speed", 0) or 0),
                    queue_position=int(getattr(msg, "num_queued_uploads", 0) or 0),
                    private=is_private,
                ))

        if not records:
            return None

        added = entry.add(msg, username, records)

        if not added:
            return None

        return {
            "token": token,
            "term": entry.term,
            "user": username,
            "added": added,
            "total": entry.total,
        }

    # -- paged reads ------------------------------------------------------

    def results_page(self, token: int, offset: int = 0, limit: int = 500) -> dict | None:

        entry = self.get(token)

        if entry is None:
            return None

        offset = max(0, int(offset))
        limit = max(1, int(limit))
        page = entry.flat[offset:offset + limit]

        return {
            "token": token,
            "total": entry.total,
            "offset": offset,
            "limit": limit,
            "results": [record.to_dict() for record in page],
        }

    def users_page(self, token: int, offset: int = 0, limit: int = 200) -> dict | None:

        entry = self.get(token)

        if entry is None:
            return None

        offset = max(0, int(offset))
        limit = max(1, int(limit))
        users = entry.sorted_users

        return {
            "token": token,
            "total": len(users),
            "offset": offset,
            "limit": limit,
            "users": [bucket.summary() for bucket in users[offset:offset + limit]],
        }

    def files_page(self, token: int, username: str, folder: str | None = None,
                   offset: int = 0, limit: int = 500) -> dict | None:

        entry = self.get(token)

        if entry is None:
            return None

        bucket = entry.users.get(username)

        if bucket is None:
            return {"token": token, "username": username, "folder": folder or "",
                    "total": 0, "offset": 0, "limit": limit, "files": []}

        offset = max(0, int(offset))
        limit = max(1, int(limit))

        if folder is None:
            folders = list(bucket.folders)
            return {
                "token": token,
                "username": username,
                "total": len(folders),
                "offset": offset,
                "limit": limit,
                "folders": {name: len(bucket.folders[name]) for name in folders[offset:offset + limit]},
            }

        files = bucket.folders.get(folder, [])

        return {
            "token": token,
            "username": username,
            "folder": folder,
            "total": len(files),
            "offset": offset,
            "limit": limit,
            "files": [record.to_dict() for record in files[offset:offset + limit]],
        }

    # -- events -----------------------------------------------------------

    def _on_remove_search(self, token: int) -> None:

        self.remove(token)

    def _on_server_disconnect(self, _msg=None) -> None:

        log.add_debug("Engine API: disconnected, keeping %s search result set(s)", len(self._entries))


STORE = SearchStore()


def store() -> SearchStore:
    return STORE
