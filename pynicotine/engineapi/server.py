# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Local HTTP API for a native front end.

The GTK client and a future SwiftUI app are both just front ends; this exposes
the engine over a token-protected HTTP/JSON surface on loopback so the native
app can be built without reimplementing the Soulseek protocol.

Start it from the environment:

    NICOTINE_API_PORT=8766 NICOTINE_API_TOKEN=secret \
        python -m pynicotine -n --config ... --user-data ...

Endpoints (all read-only except the two POSTs):

    GET  /health
    GET  /state
    GET  /users/<user>/summary
    GET  /users/<user>/folders?offset=0&limit=200
    GET  /users/<user>/files?folder=<path>&offset=0&limit=500
    POST /users/<user>/browse
    GET  /downloads?offset=0&limit=500
    GET  /crate
    POST /crate/<id>/separate
"""

from __future__ import annotations

import json
import os
import threading
import urllib.parse

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pynicotine

from pynicotine.engineapi.serialize import (
    crate_track_dict,
    file_dict,
    transfer_dict,
)

DEFAULT_PORT = 8766
DEFAULT_LIMIT = 200
MAX_LIMIT = 5000

_SERVER: ThreadingHTTPServer | None = None
_TOKEN = ""


def _core():
    from pynicotine.core import core

    return core


class Handler(BaseHTTPRequestHandler):
    server_version = "NicotineEngine/1.0"

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

    def _authorized(self) -> bool:
        if not _TOKEN:
            return True

        return self.headers.get("Authorization") == f"Bearer {_TOKEN}"

    def _query(self) -> dict:
        parsed = urllib.parse.urlparse(self.path)
        return {key: values[-1] for key, values in urllib.parse.parse_qs(parsed.query).items()}

    @staticmethod
    def _int(query: dict, key: str, default: int) -> int:
        try:
            return max(0, min(MAX_LIMIT, int(query.get(key, default))))

        except (TypeError, ValueError):
            return default

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

        if not self._authorized():
            return self._error(HTTPStatus.UNAUTHORIZED, "bad or missing token")

        try:
            return self._route_get(parts)

        except Exception as error:  # noqa: BLE001 - never leak a stack trace
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

    def _route_get(self, parts: list[str]) -> None:

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
            })

        if len(parts) == 3 and parts[0] == "users" and parts[2] == "summary":
            summary = core.userbrowse.user_summary(parts[1])

            if summary is None:
                return self._error(HTTPStatus.NOT_FOUND, "user has not been browsed")

            return self._reply(HTTPStatus.OK, summary)

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

            return self._reply(HTTPStatus.OK, {
                "total": len(tracks),
                "tracks": [crate_track_dict(track) for track in tracks],
            })

        return self._error(HTTPStatus.NOT_FOUND, "unknown endpoint")

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            return self._error(HTTPStatus.UNAUTHORIZED, "bad or missing token")

        parsed = urllib.parse.urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]

        try:
            return self._route_post(parts)

        except Exception as error:  # noqa: BLE001
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

    def _route_post(self, parts: list[str]) -> None:

        from pynicotine.core import core
        from pynicotine.events import events

        if len(parts) == 3 and parts[0] == "users" and parts[2] == "browse":
            username = parts[1]

            # browse_user() creates the BrowsedUser entry (and handles browsing
            # our own shares); request_user_shares alone would update nothing.
            events.invoke_main_thread(
                lambda: core.userbrowse.browse_user(username, new_request=True, switch_page=False)
            )
            return self._reply(HTTPStatus.ACCEPTED, {"requested": username})

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
