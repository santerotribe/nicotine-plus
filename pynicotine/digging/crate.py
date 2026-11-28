# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""The crate: tracks we are auditioning, keeping and separating."""

from __future__ import annotations

import json
import re
import time
import uuid

from dataclasses import asdict, dataclass, field
from pathlib import Path

STATUS_CANDIDATE = "candidate"
STATUS_KEPT = "kept"
STATUS_DOWNLOADING = "downloading"
STATUS_DOWNLOADED = "downloaded"
STATUS_SEPARATING = "separating"
STATUS_READY = "ready"          # stems on disk
STATUS_SCHEDULED = "scheduled"  # placed in a Live set
STATUS_FAILED = "failed"

KIND_SAMPLE = "sample"
KIND_DJ = "dj"
KINDS = (KIND_SAMPLE, KIND_DJ)


def slugify(value: str, limit: int = 60) -> str:
    stem = Path(value).stem if Path(value).suffix else value
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", stem).strip("-").lower()
    return (cleaned or "track")[:limit]


@dataclass
class CrateTrack:
    username: str = ""
    virtual_path: str = ""
    filename: str = ""
    size: int = 0
    kind: str = KIND_SAMPLE

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    local_path: str = ""
    bpm: float = 0.0
    duration: float = 0.0
    status: str = STATUS_CANDIDATE
    stems: dict[str, str] = field(default_factory=dict)
    als_path: str = ""
    error: str = ""
    added: float = field(default_factory=time.time)

    @property
    def display_name(self) -> str:
        return self.filename or Path(self.virtual_path).name

    @property
    def folder(self) -> str:
        return str(Path(self.virtual_path).parent)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "CrateTrack":
        known = {field_name for field_name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in payload.items() if key in known})


class Crate:
    """JSON-backed list of tracks. Safe to call from a GUI thread or CLI."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else None
        self.tracks: list[CrateTrack] = []
        self.load()

    def __len__(self) -> int:
        return len(self.tracks)

    def __iter__(self):
        return iter(self.tracks)

    def add(self, track: CrateTrack) -> CrateTrack:
        for existing in self.tracks:
            if existing.username == track.username and existing.virtual_path == track.virtual_path:
                return existing

        self.tracks.append(track)
        self.save()
        return track

    def remove(self, track_id: str) -> bool:
        before = len(self.tracks)
        self.tracks = [track for track in self.tracks if track.id != track_id]

        if len(self.tracks) != before:
            self.save()
            return True

        return False

    def get(self, track_id: str) -> CrateTrack | None:
        for track in self.tracks:
            if track.id == track_id:
                return track

        return None

    def by_status(self, *statuses: str) -> list[CrateTrack]:
        return [track for track in self.tracks if track.status in statuses]

    def by_kind(self, kind: str) -> list[CrateTrack]:
        return [track for track in self.tracks if track.kind == kind]

    def set_kind(self, track_id: str, kind: str) -> CrateTrack | None:
        if kind not in KINDS:
            raise ValueError(f"unknown crate kind: {kind}")

        track = self.get(track_id)

        if track is None:
            return None

        track.kind = kind
        self.save()
        return track

    def load(self) -> None:
        if not self.path or not self.path.is_file():
            return

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))

        except (OSError, ValueError):
            return

        self.tracks = [
            CrateTrack.from_dict(entry) for entry in payload.get("tracks", [])
            if isinstance(entry, dict)
        ]

    def save(self) -> None:
        if not self.path:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "tracks": [track.to_dict() for track in self.tracks]}
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)
