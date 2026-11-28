# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""The collective ledger: who found which track, in a file the crew can sync.

One JSON file, last-write-wins per (peer, virtual_path). Point
`rolodex_path` at a shared folder (iCloud Drive, Dropbox, the studio machine)
and every member's keeps appear in everyone's Rolodex. The crate remains the
member's own working set; this file is the memory of the group.
"""

from __future__ import annotations

import json
import os
import tempfile
import time

from pathlib import Path


def default_path() -> Path:
    return Path.home() / "Documents" / "Tribe Seek" / "rolodex.json"


class Ledger:

    def __init__(self, path: str | Path | None, member: str) -> None:
        self.path = Path(path).expanduser() if path else default_path()
        self.member = member or "unknown"
        self.entries: dict[tuple[str, str], dict] = {}
        self.load()

    def load(self) -> None:

        if not self.path.is_file():
            return

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))

        except (OSError, ValueError):
            return

        entries = payload.get("entries") if isinstance(payload, dict) else None

        for entry in entries or []:
            if not isinstance(entry, dict) or not entry.get("peer"):
                continue

            key = (str(entry.get("peer")), str(entry.get("virtual_path") or ""))
            self.entries[key] = entry

    def add(self, peer: str, virtual_path: str, folder: str = "",
            filename: str = "", kind: str = "sample") -> dict:
        """Record a keep. Re-reads first so a synced file's other entries survive."""

        self.load()

        entry = {
            "peer": peer,
            "virtual_path": virtual_path,
            "folder": folder,
            "filename": filename,
            "kind": kind,
            "found_by": self.member,
            "added_at": time.time(),
        }

        self.entries[(peer, virtual_path)] = entry
        self.save()

        return entry

    def star(self, peer: str, starred: bool) -> None:
        """One star per member, so two people can star the same seller."""

        self.load()

        key = (peer, f"star:{self.member}")

        if starred:
            self.entries[key] = {
                "peer": peer,
                "virtual_path": key[1],
                "folder": "",
                "filename": "",
                "kind": "star",
                "found_by": self.member,
                "added_at": time.time(),
            }
        else:
            self.entries.pop(key, None)

        self.save()

    def save(self) -> None:

        self.path.parent.mkdir(parents=True, exist_ok=True)

        payload = {"version": 1, "entries": list(self.entries.values())}

        descriptor, temporary = tempfile.mkstemp(
            dir=self.path.parent, prefix=".rolodex-", suffix=".json.tmp")

        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(temporary, self.path)

        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def as_list(self) -> list[dict]:
        return sorted(
            self.entries.values(),
            key=lambda entry: float(entry.get("added_at") or 0),
            reverse=True,
        )
