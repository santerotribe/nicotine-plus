# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Local HTTP API for a native front end.

The GTK client and a future SwiftUI app are both just front ends; this exposes
the engine over a token-protected HTTP/JSON surface on loopback so the native
app can be built without reimplementing the Soulseek protocol.

Start it from the environment:

    NICOTINE_API_PORT=8766 NICOTINE_API_TOKEN=secret \
        python -m pynicotine -n --config ... --user-data ...

Endpoints:

    GET    /health
    GET    /state
    GET    /events                          Server-Sent Events (see hub.py)
    GET    /users/<user>/summary
    GET    /users/<user>/folders?offset=0&limit=200
    GET    /users/<user>/files?folder=<path>&offset=0&limit=500
    POST   /users/<user>/browse
    GET    /downloads?offset=0&limit=500
    GET    /crate
    POST   /crate/<id>/separate
    GET    /search                         tracked searches
    POST   /search                         {"term": "...", "mode": "global"}
    GET    /search/<token>                 counters
    GET    /search/<token>/results?offset=0&limit=500
    GET    /search/<token>/users?offset=0&limit=200
    GET    /search/<token>/files?user=<u>&folder=<f>&offset=0&limit=500
    POST   /search/<token>/stop
    DELETE /search/<token>
    GET    /audition                       active audition sessions
    POST   /audition                       start one for a browsed file
    GET    /audition/<id>                  resolved playback source
    POST   /audition/<id>/keep             add to the crate
    DELETE /audition/<id>                  stop and clean up
"""

from __future__ import annotations

import json
import os
import queue
import socket
import threading
import time
import urllib.parse

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pynicotine

from pynicotine.engineapi.audition import audition_sessions
from pynicotine.engineapi.hub import event_hub, type_filter
from pynicotine.engineapi.searchstore import store as search_store
from pynicotine.engineapi.serialize import (
    crate_track_dict,
    file_dict,
    transfer_dict,
)

DEFAULT_PORT = 8766
DEFAULT_LIMIT = 200
MAX_LIMIT = 5000
MAX_BODY_BYTES = 1024 * 1024
HEARTBEAT_SECONDS = 15.0
MAIN_THREAD_TIMEOUT = 8.0

_SERVER: ThreadingHTTPServer | None = None
_TOKEN = ""


def _core():
    from pynicotine.core import core

    return core


class Handler(BaseHTTPRequestHandler):
    server_version = "NicotineEngine/1.0"
    protocol_version = "HTTP/1.1"
    timeout = 60  # idle keep-alive connections must not pin a thread forever

    def log_message(self, fmt, *args):  # noqa: A003
        return

    # -- helpers -----------------------------------------------------------

    def _reply(self, status: int, payload) -> None:
        body = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._reply(status, {"error": message})

    def _authorized(self, query: dict | None = None) -> bool:
        if not _TOKEN:
            return True

        if self.headers.get("Authorization") == f"Bearer {_TOKEN}":
            return True

        # EventSource-style clients cannot set headers; the token may also be
        # passed in the query string, loopback only.
        return query is not None and query.get("token") == _TOKEN

    def _query(self) -> dict:
        parsed = urllib.parse.urlparse(self.path)
        return {key: values[-1] for key, values in urllib.parse.parse_qs(parsed.query).items()}

    @staticmethod
    def _int(query: dict, key: str, default: int) -> int:
        try:
            return max(0, min(MAX_LIMIT, int(query.get(key, default))))

        except (TypeError, ValueError):
            return default

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)

        except (TypeError, ValueError):
            length = 0

        if length <= 0:
            return {}

        if length > MAX_BODY_BYTES:
            raise ValueError("request body too large")

        raw = self.rfile.read(length)

        try:
            payload = json.loads(raw.decode("utf-8"))

        except ValueError as error:
            raise ValueError(f"invalid JSON body: {error}") from error

        if not isinstance(payload, dict):
            raise ValueError("expected a JSON object")

        return payload

    @staticmethod
    def _invoke(callback, timeout: float = MAIN_THREAD_TIMEOUT):
        """Run a callback on the engine thread and return its value.

        Engine mutations must happen where the rest of the engine runs; HTTP
        handlers are separate threads. If we already are on the engine thread
        (tests), call directly.
        """

        if threading.current_thread() is threading.main_thread():
            return callback()

        from pynicotine.events import events

        done = threading.Event()
        box: dict = {}

        def runner() -> None:

            try:
                box["value"] = callback()

            except BaseException as error:  # noqa: BLE001 - re-raised below
                box["error"] = error

            finally:
                done.set()

        events.invoke_main_thread(runner)

        if not done.wait(timeout):
            raise TimeoutError("the engine did not answer in time")

        error = box.get("error")

        if error is not None:
            raise error

        return box.get("value")

    def _sse_write(self, payload: dict) -> None:

        data = json.dumps(payload, default=str)
        seq = payload.get("seq")
        prefix = f"id: {seq}\n" if seq else ""
        self._sse_chunk(f"{prefix}event: {payload.get('type', 'message')}\ndata: {data}\n\n".encode())

    def _sse_chunk(self, body: bytes) -> None:
        """Write one HTTP/1.1 chunk.

        SSE has no Content-Length, so without chunked framing URLSession waits
        for the connection to close before delivering anything. Chunked means a
        native client sees events as they happen; curl is equally happy.
        """

        self.wfile.write(f"{len(body):X}\r\n".encode() + body + b"\r\n")
        self.wfile.flush()

    def _stream_events(self, query: dict) -> None:
        """Hold the connection open and write events until the client leaves."""

        subscriber = event_hub().subscribe(*type_filter(query.get("types", "")))

        try:
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        except OSError:
            pass

        # Endless response, framed with chunked transfer encoding so clients do
        # not wait for a close that never comes.
        self.protocol_version = "HTTP/1.1"

        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            hello = {"type": "hello", "seq": 0, "time": int(time.time())}
            hello.update(event_hub().snapshot())
            self._sse_write(hello)

            while True:
                try:
                    payload = subscriber.queue.get(timeout=HEARTBEAT_SECONDS)

                except queue.Empty:
                    self._sse_chunk(b": ping\n\n")
                    continue

                dropped = subscriber.take_dropped()

                if dropped:
                    self._sse_write({"type": "gap", "dropped": dropped})

                self._sse_write(payload)

        except OSError:
            pass

        finally:
            event_hub().unsubscribe(subscriber)

    # -- routing -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]

        if parsed.path == "/health":
            core = _core()

            return self._reply(HTTPStatus.OK, {
                "ok": True,
                "version": pynicotine.__version__,
                "logged_in": bool(core.users.login_status),
                "username": core.users.login_username,
            })

        query = self._query()

        if not self._authorized(query):
            return self._error(HTTPStatus.UNAUTHORIZED, "bad or missing token")

        if parts == ["events"]:
            return self._stream_events(query)

        try:
            return self._route_get(parts)

        except Exception as error:  # noqa: BLE001 - never leak a stack trace
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

    def _route_get(self, parts: list[str]) -> None:  # pylint: disable=too-many-return-statements

        core = _core()
        query = self._query()

        if parts == ["state"]:
            userbrowse = core.userbrowse

            return self._reply(HTTPStatus.OK, {
                "username": core.users.login_username,
                "status": str(core.users.login_status),
                "privileges_seconds": core.users.privileges_left,
                "downloads": len(core.downloads.transfers),
                "browsed_users": list(userbrowse.users),
                "searches": len(search_store().summaries()),
                "auditions": len(audition_sessions().summaries()),
                "event_subscribers": event_hub().subscriber_count,
            })

        if len(parts) == 3 and parts[0] == "users" and parts[2] == "summary":
            summary = core.userbrowse.user_summary(parts[1])

            if summary is None:
                return self._error(HTTPStatus.NOT_FOUND, "user has not been browsed")

            return self._reply(HTTPStatus.OK, summary)

        if len(parts) == 3 and parts[0] == "users" and parts[2] == "status":
            from pynicotine.slskmessages import UserStatus

            status = core.users.statuses.get(parts[1])

            try:
                name = UserStatus(int(status)).name.lower() if status is not None else "unknown"
            except (TypeError, ValueError):
                name = "unknown"

            return self._reply(HTTPStatus.OK, {"username": parts[1], "status": name})

        if len(parts) == 3 and parts[0] == "users" and parts[2] == "folders":
            offset = self._int(query, "offset", 0)
            limit = self._int(query, "limit", DEFAULT_LIMIT)
            page = core.userbrowse.folder_page(parts[1], offset, limit)

            if page is None:
                return self._error(HTTPStatus.NOT_FOUND, "user has not been browsed")

            return self._reply(HTTPStatus.OK, page)

        if len(parts) == 3 and parts[0] == "users" and parts[2] == "files":
            offset = self._int(query, "offset", 0)
            limit = self._int(query, "limit", 500)
            folder = query.get("folder", "")
            page = core.userbrowse.file_page(parts[1], folder, offset, limit)

            if page is None:
                return self._error(HTTPStatus.NOT_FOUND, "user has not been browsed")

            page["files"] = [file_dict(entry) for entry in page["files"]]
            return self._reply(HTTPStatus.OK, page)

        if parts == ["downloads"]:
            offset = self._int(query, "offset", 0)
            limit = self._int(query, "limit", 500)
            transfers = list(core.downloads.transfers.values())
            page = transfers[offset:offset + limit]

            return self._reply(HTTPStatus.OK, {
                "total": len(transfers),
                "offset": offset,
                "limit": limit,
                "downloads": [transfer_dict(entry) for entry in page],
            })

        if parts == ["crate"]:
            from pynicotine.digging.actions import crate_for

            tracks = crate_for().tracks
            kind = query.get("kind")

            if kind:
                tracks = [track for track in tracks if track.kind == kind]

            return self._reply(HTTPStatus.OK, {
                "total": len(tracks),
                "tracks": [crate_track_dict(track) for track in tracks],
            })

        if parts == ["search"]:
            summaries = search_store().summaries()

            return self._reply(HTTPStatus.OK, {"total": len(summaries), "searches": summaries})

        if len(parts) >= 2 and parts[0] == "search":
            return self._route_search_get(parts, query)

        if parts == ["audition"]:
            summaries = audition_sessions().summaries()

            return self._reply(HTTPStatus.OK, {"total": len(summaries), "auditions": summaries})

        if len(parts) == 2 and parts[0] == "audition":
            session = audition_sessions().get(parts[1])

            if session is None:
                return self._error(HTTPStatus.NOT_FOUND, "unknown audition")

            return self._reply(HTTPStatus.OK, session.state())

        return self._error(HTTPStatus.NOT_FOUND, "unknown endpoint")

    def _route_search_get(self, parts: list[str], query: dict) -> None:

        try:
            token = int(parts[1])

        except (TypeError, ValueError):
            return self._error(HTTPStatus.BAD_REQUEST, "invalid search token")

        store = search_store()
        offset = self._int(query, "offset", 0)
        limit = self._int(query, "limit", 500)

        if len(parts) == 2:
            entry = store.get(token)

            if entry is None:
                return self._error(HTTPStatus.NOT_FOUND, "unknown search")

            return self._reply(HTTPStatus.OK, entry.summary())

        if parts[2] == "results":
            page = store.results_page(token, offset, limit)

            if page is None:
                return self._error(HTTPStatus.NOT_FOUND, "unknown search")

            return self._reply(HTTPStatus.OK, page)

        if parts[2] == "users":
            page = store.users_page(token, offset, limit)

            if page is None:
                return self._error(HTTPStatus.NOT_FOUND, "unknown search")

            return self._reply(HTTPStatus.OK, page)

        if parts[2] == "files":
            username = query.get("user", "")

            if not username:
                return self._error(HTTPStatus.BAD_REQUEST, "user is required")

            folder = query.get("folder")
            page = store.files_page(token, username, folder, offset, limit)

            if page is None:
                return self._error(HTTPStatus.NOT_FOUND, "unknown search")

            return self._reply(HTTPStatus.OK, page)

        return self._error(HTTPStatus.NOT_FOUND, "unknown endpoint")

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized(self._query()):
            return self._error(HTTPStatus.UNAUTHORIZED, "bad or missing token")

        parsed = urllib.parse.urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]

        try:
            return self._route_post(parts)

        except ValueError as error:
            return self._error(HTTPStatus.BAD_REQUEST, str(error))

        except Exception as error:  # noqa: BLE001
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._authorized(self._query()):
            return self._error(HTTPStatus.UNAUTHORIZED, "bad or missing token")

        parsed = urllib.parse.urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]

        try:
            return self._route_delete(parts)

        except ValueError as error:
            return self._error(HTTPStatus.BAD_REQUEST, str(error))

        except Exception as error:  # noqa: BLE001
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

    def _route_delete(self, parts: list[str]) -> None:

        from pynicotine.core import core

        if len(parts) == 2 and parts[0] == "search":
            try:
                token = int(parts[1])

            except (TypeError, ValueError):
                return self._error(HTTPStatus.BAD_REQUEST, "invalid search token")

            if search_store().get(token) is None:
                return self._error(HTTPStatus.NOT_FOUND, "unknown search")

            self._invoke(lambda: core.search.remove_search(token))
            search_store().remove(token)
            return self._reply(HTTPStatus.OK, {"stopped": token})

        if len(parts) == 2 and parts[0] == "crate":
            from pynicotine.digging.actions import crate_for

            crate = crate_for()

            if crate.get(parts[1]) is None:
                return self._error(HTTPStatus.NOT_FOUND, "unknown crate track")

            self._invoke(lambda: crate.remove(parts[1]))
            return self._reply(HTTPStatus.OK, {"removed": parts[1]})

        if len(parts) == 2 and parts[0] == "audition":
            session = audition_sessions().get(parts[1])

            if session is None:
                return self._error(HTTPStatus.NOT_FOUND, "unknown audition")

            self._invoke(lambda: audition_sessions().close(session.id))
            return self._reply(HTTPStatus.OK, {"closed": session.id})

        return self._error(HTTPStatus.NOT_FOUND, "unknown endpoint")

    def _route_post(self, parts: list[str]) -> None:

        from pynicotine.core import core
        from pynicotine.events import events

        if parts == ["login"]:
            from pynicotine.core import core

            if core.users.login_status != 0:
                return self._reply(HTTPStatus.OK, {"connected": True})

            # After "someone logged in elsewhere" the engine deliberately stops
            # retrying; a front end can ask it to try again once that client quits.
            self._invoke(core.connect)
            return self._reply(HTTPStatus.ACCEPTED, {"connecting": True})

        if len(parts) == 3 and parts[0] == "users" and parts[2] == "status":
            username = parts[1]
            self._invoke(lambda: core.users.request_user_status(username))
            return self._reply(HTTPStatus.ACCEPTED, {"requested": username})

        if len(parts) == 3 and parts[0] == "users" and parts[2] == "browse":
            username = parts[1]

            # browse_user() creates the BrowsedUser entry (and handles browsing
            # our own shares); request_user_shares alone would update nothing.
            events.invoke_main_thread(
                lambda: core.userbrowse.browse_user(username, new_request=True, switch_page=False)
            )
            return self._reply(HTTPStatus.ACCEPTED, {"requested": username})

        if parts == ["search"]:
            return self._create_search()

        if len(parts) == 3 and parts[0] == "search" and parts[2] == "stop":
            try:
                token = int(parts[1])

            except (TypeError, ValueError):
                return self._error(HTTPStatus.BAD_REQUEST, "invalid search token")

            if search_store().get(token) is None:
                return self._error(HTTPStatus.NOT_FOUND, "unknown search")

            self._invoke(lambda: core.search.remove_search(token))
            search_store().remove(token)
            return self._reply(HTTPStatus.OK, {"stopped": token})

        if parts == ["audition"]:
            return self._create_audition()

        if len(parts) == 3 and parts[0] == "audition" and parts[2] == "keep":
            session = audition_sessions().get(parts[1])

            if session is None:
                return self._error(HTTPStatus.NOT_FOUND, "unknown audition")

            from pynicotine.digging.crate import KINDS

            payload = self._body()
            kind = str(payload.get("kind") or "sample")

            if kind not in KINDS:
                return self._error(HTTPStatus.BAD_REQUEST, f"unknown crate kind: {kind}")

            track = self._invoke(lambda: session.keep(kind))
            return self._reply(HTTPStatus.ACCEPTED, {"track": track, "audition": session.summary()})

        if parts == ["crate", "keep"]:
            from pynicotine.core import core
            from pynicotine.digging.actions import TrackSource, keep_source
            from pynicotine.digging.crate import KINDS
            from pynicotine.digging.settings import DiggingSettings
            from pynicotine.engineapi.serialize import crate_track_dict
            from pynicotine.slskmessages import FileAttributes

            payload = self._body()
            items = payload.get("files") or []
            kind = str(payload.get("kind") or "sample")

            if kind not in KINDS:
                return self._error(HTTPStatus.BAD_REQUEST, f"unknown crate kind: {kind}")

            if not isinstance(items, list) or not items:
                return self._error(HTTPStatus.BAD_REQUEST, "files must be a non-empty list")

            def keep_all() -> list[dict]:

                settings = DiggingSettings.load()
                kept = []

                for item in items:
                    if not isinstance(item, dict):
                        continue

                    attributes = item.get("attributes") or {}
                    source = TrackSource(
                        username=str(item.get("username") or ""),
                        folder_path=str(item.get("folder") or ""),
                        filename=str(item.get("filename") or ""),
                        size=int(item.get("size") or 0),
                        attributes=FileAttributes(
                            bitrate=attributes.get("bitrate"),
                            length=attributes.get("length"),
                            vbr=attributes.get("vbr"),
                            sample_rate=attributes.get("sample_rate"),
                            bit_depth=attributes.get("bit_depth"),
                        ),
                    )

                    if not source.username or not source.filename:
                        continue

                    kept.append(crate_track_dict(keep_source(core, source, settings, kind=kind)))

                return kept

            kept = self._invoke(keep_all)

            return self._reply(HTTPStatus.ACCEPTED, {"kept": kept, "count": len(kept)})

        if len(parts) == 3 and parts[0] == "crate" and parts[2] == "kind":
            from pynicotine.digging.actions import crate_for

            payload = self._body()
            kind = str(payload.get("kind") or "")
            crate = crate_for()

            if crate.get(parts[1]) is None:
                return self._error(HTTPStatus.NOT_FOUND, "unknown crate track")

            track = self._invoke(lambda: crate.set_kind(parts[1], kind))
            return self._reply(HTTPStatus.OK, {"track": crate_track_dict(track)})

        if len(parts) == 3 and parts[0] == "crate" and parts[2] == "separate":
            from pynicotine.digging.actions import crate_for
            from pynicotine.digging.service import start_service

            track_id = parts[1]
            track = next((entry for entry in crate_for().tracks if entry.id == track_id), None)

            if track is None:
                return self._error(HTTPStatus.NOT_FOUND, "unknown crate track")

            start_service().kick(track)
            return self._reply(HTTPStatus.ACCEPTED, {"separating": track.filename})

        return self._error(HTTPStatus.NOT_FOUND, "unknown endpoint")

    # -- action endpoints --------------------------------------------------

    def _create_search(self) -> None:

        from pynicotine.core import core
        from pynicotine.search import SearchMode
        from pynicotine.slskmessages import UserStatus

        payload = self._body()
        term = str(payload.get("term") or "").strip()

        if not term:
            return self._error(HTTPStatus.BAD_REQUEST, "term is required")

        raw_mode = str(payload.get("mode") or SearchMode.GLOBAL).lower()

        try:
            mode = SearchMode(raw_mode)

        except ValueError:
            return self._error(HTTPStatus.BAD_REQUEST, f"unknown search mode: {raw_mode}")

        if mode == SearchMode.WISHLIST:
            return self._error(HTTPStatus.BAD_REQUEST, "wishlist searches are not supported here")

        room = payload.get("room") or None
        users = payload.get("users") or None

        if users is not None and not isinstance(users, list):
            return self._error(HTTPStatus.BAD_REQUEST, "users must be a list")

        if mode == SearchMode.USER and not users:
            return self._error(HTTPStatus.BAD_REQUEST, "users is required for user searches")

        if mode == SearchMode.ROOMS and not room:
            return self._error(HTTPStatus.BAD_REQUEST, "room is required for room searches")

        if core.users.login_status == UserStatus.OFFLINE:
            return self._error(HTTPStatus.CONFLICT, "not logged in")

        def start_search() -> dict:

            token = core.search.do_search(
                term, mode, room=room, users=users, switch_page=False, notify_frontend=False)
            search = core.search.searches.get(token)

            if search is None:
                raise RuntimeError("search was not registered")

            # Registered on the engine thread, before any result can arrive, so
            # the first peer response is never lost.
            return search_store().create(
                token, search.term, str(search.mode), search.included_words, search.excluded_words).summary()

        summary = self._invoke(start_search)
        event_hub().publish("search_started", token=summary["token"], term=summary["term"], mode=summary["mode"])
        return self._reply(HTTPStatus.CREATED, summary)

    def _create_audition(self) -> None:

        from pynicotine.core import core

        payload = self._body()
        username = str(payload.get("username") or "").strip()
        virtual_path = str(payload.get("virtual_path") or "").strip()

        if not username or not virtual_path:
            return self._error(HTTPStatus.BAD_REQUEST, "username and virtual_path are required")

        folder, _separator, basename = virtual_path.rpartition("\\")
        filename = str(payload.get("filename") or basename or virtual_path)
        size = int(payload.get("size") or 0)
        attributes = _attributes(payload)
        duration = float(payload.get("duration") or getattr(attributes, "length", 0) or 0.0)

        def start_session() -> object:

            local_path = ""

            if username == core.users.login_username:
                # Our own shares are already on disk: audition the real file.
                try:
                    local_folder = core.shares.virtual2real(folder)
                    candidate = os.path.join(local_folder, filename)

                    if os.path.isfile(candidate):
                        local_path = candidate

                except Exception:  # noqa: BLE001 - fall back to catalogue/peer
                    local_path = ""

            return audition_sessions().start(
                username=username,
                virtual_path=virtual_path,
                filename=filename,
                size=size,
                attributes=attributes,
                duration_hint=duration,
                local_path=local_path,
            )

        session = self._invoke(start_session)
        return self._reply(HTTPStatus.CREATED, session.state())


def _attributes(payload: dict):
    """Build the file attribute object the transfer layer expects."""

    from pynicotine.slskmessages import FileAttributes

    fields = payload.get("attributes") or {}

    def pick(name: str) -> int | None:

        value = fields.get(name, payload.get(name))

        if value is None:
            return None

        try:
            return int(value)

        except (TypeError, ValueError):
            return None

    try:
        return FileAttributes(
            bitrate=pick("bitrate"),
            length=pick("length"),
            vbr=pick("vbr"),
            sample_rate=pick("sample_rate"),
            bit_depth=pick("bit_depth"),
        )

    except TypeError:
        return None


def start(port: int = DEFAULT_PORT, token: str = "", host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """Start the API server in a daemon thread. Loopback only by default."""

    global _SERVER, _TOKEN

    if _SERVER is not None:
        return _SERVER

    _TOKEN = token or os.environ.get("NICOTINE_API_TOKEN", "")
    server = ThreadingHTTPServer((host, port), Handler)
    _SERVER = server
    thread = threading.Thread(target=server.serve_forever, name="engine-api", daemon=True)
    thread.start()

    # Push channel and engine-side search results only cost anything once the
    # API is actually enabled.
    event_hub().start()
    search_store().start()

    from pynicotine.logfacility import log

    log.add(f"Engine API listening on http://{host}:{port}"
            f"{' (token required)' if _TOKEN else ' (no token)'}")
    return server


def maybe_start() -> ThreadingHTTPServer | None:
    """Start only when NICOTINE_API_PORT is set."""

    port = os.environ.get("NICOTINE_API_PORT")

    if not port:
        return None

    try:
        return start(int(port))

    except (OSError, ValueError) as error:
        from pynicotine.logfacility import log

        log.add(f"Engine API could not start: {error}")
        return None


def stop() -> None:
    global _SERVER

    if _SERVER is not None:
        _SERVER.shutdown()
        _SERVER.server_close()
        _SERVER = None
