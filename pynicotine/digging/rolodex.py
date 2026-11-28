# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""The collective ledger: one small file per entry, safe to sync.

A single JSON file loses entries when two members write at once: each save
rewrites the whole file. This ledger instead keeps one `<hash>.json` per entry
in a directory, so different members' keeps never collide and a synced folder
can merge them file by file. Same entry, last write wins.

`rolodex_path` may name that directory, or a legacy `rolodex.json`; a legacy
file is migrated into the sibling directory on first use and then left alone.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time

from pathlib import Path


def default_path() -> Path:
    return Path.home() / "Documents" / "Tribe Seek" / "rolodex"


class Ledger:

    def __init__(self, path: str | Path | None, member: str,
                 member_id: str = "") -> None:

        raw = Path(path).expanduser() if path else default_path()

        if raw.suffix.lower() == ".json":
            self._legacy = raw
            self.path = raw.with_suffix("")
        else:
            self._legacy = None
            self.path = raw

        self.member = member or "unknown"
        self.member_id = member_id or self.member
        self.entries: dict[tuple[str, str], dict] = {}

        self.load()

        if self._legacy is not None and self._legacy.is_file():
            self._migrate()

    def load(self) -> None:

        self.entries = {}

        if not self.path.is_dir():
            return

        for file in self.path.glob("*.json"):
            try:
                entry = json.loads(file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue

            if isinstance(entry, dict) and entry.get("peer"):
                self.entries[
                    (str(entry["peer"]), str(entry.get("virtual_path") or ""))
                ] = entry

    def add(self, peer: str, virtual_path: str, folder: str = "",
            filename: str = "", kind: str = "sample") -> dict:

        entry = {
            "peer": peer,
            "virtual_path": virtual_path,
            "folder": folder,
            "filename": filename,
            "kind": kind,
            "found_by": self.member,
            "found_by_id": self.member_id,
            "added_at": time.time(),
        }

        self.entries[(peer, virtual_path)] = entry
        self._write(entry)
        return entry

    def star(self, peer: str, starred: bool) -> None:
        """One star per member, so two people can star the same seller."""

        key = (peer, f"star:{self.member_id}")

        if starred:
            entry = {
                "peer": peer,
                "virtual_path": key[1],
                "folder": "",
                "filename": "",
                "kind": "star",
                "found_by": self.member,
                "found_by_id": self.member_id,
                "added_at": time.time(),
            }

            self.entries[key] = entry
            self._write(entry)
            return

        self.entries.pop(key, None)
        self._remove(key)

    def as_list(self) -> list[dict]:
        self.load()

        return sorted(
            self.entries.values(),
            key=lambda entry: float(entry.get("added_at") or 0),
            reverse=True,
        )

    # -- storage ----------------------------------------------------------

    def _filename(self, key: tuple[str, str]) -> Path:
        digest = hashlib.sha1(f"{key[0]}\0{key[1]}".encode("utf-8")).hexdigest()

        return self.path / f"{digest[:32]}.json"

    def _write(self, entry: dict) -> None:

        self.path.mkdir(parents=True, exist_ok=True)

        descriptor, temporary = tempfile.mkstemp(
            dir=self.path, prefix=".entry-", suffix=".json.tmp")

        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(entry, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(temporary, self._filename(
                (str(entry["peer"]), str(entry.get("virtual_path") or ""))))

        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _remove(self, key: tuple[str, str]) -> None:
        try:
            self._filename(key).unlink()
        except FileNotFoundError:
            pass

    def _migrate(self) -> None:

        try:
            payload = json.loads(self._legacy.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return

        entries = payload.get("entries") if isinstance(payload, dict) else None

        for entry in entries or []:
            if not isinstance(entry, dict) or not entry.get("peer"):
                continue

            key = (str(entry["peer"]), str(entry.get("virtual_path") or ""))

            if key in self.entries:
                continue

            entry.setdefault("found_by_id", entry.get("found_by") or "unknown")
            self.entries[key] = entry
            self._write(entry)
