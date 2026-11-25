# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Runs the rest of the pipeline once a kept track finishes downloading.

Keep -> download -> separate -> Live Set should be one gesture. This service
watches finished downloads, finds the matching crate entry, runs the configured
renderer and builds (optionally opens) the Live Set.
"""

from __future__ import annotations

import threading

from pathlib import Path

from pynicotine.events import events
from pynicotine.logfacility import log
from pynicotine.transfers import TransferStatus

from pynicotine.digging import pipeline
from pynicotine.digging.actions import crate_for
from pynicotine.digging.paths import virtual_basename
from pynicotine.digging.crate import (
    STATUS_FAILED,
    STATUS_KEPT,
    STATUS_SCHEDULED,
    STATUS_SEPARATING,
)
from pynicotine.digging.settings import DiggingSettings


class PipelineService:

    def __init__(self, settings: DiggingSettings | None = None) -> None:
        self.settings = settings or DiggingSettings.load()
        self._started = False
        self._running: set[str] = set()
        self._lock = threading.Lock()

    # -- wiring -----------------------------------------------------------

    def start(self) -> None:

        if self._started:
            return

        events.connect("update-download", self._on_download_update)
        # Transfers are often auto-cleared on completion, which skips the
        # FINISHED update; the cleared transfer still tells us what to look for.
        events.connect("clear-download", self._on_download_cleared)
        self._started = True

    def kick(self, track) -> None:
        """Start processing a track whose file is already on disk."""

        path = self._local_path(track)

        if path is not None:
            self._launch(track, path)

    def _on_download_update(self, transfer, _update_parent=None) -> None:

        if transfer.status != TransferStatus.FINISHED:
            return

        track = self._find_track(transfer.username, transfer.virtual_path)

        if track is None:
            return

        path = Path(transfer.folder_path or "") / virtual_basename(transfer.virtual_path)

        if not path.is_file():
            return

        self._launch(track, path)

    def _on_download_cleared(self, transfer, _update_parent=None) -> None:

        track = self._find_track(transfer.username, transfer.virtual_path)

        if track is None:
            return

        path = Path(transfer.folder_path or "") / virtual_basename(transfer.virtual_path)

        if path.is_file():
            self._launch(track, path)

    # -- helpers ----------------------------------------------------------

    def _crate(self):
        return crate_for(self.settings)

    def _find_track(self, username: str, virtual_path: str):

        for track in self._crate().tracks:
            if track.username == username and track.virtual_path == virtual_path:
                if track.status == STATUS_KEPT and not track.stems:
                    return track

        return None

    def _local_path(self, track) -> Path | None:

        if track.local_path:
            candidate = Path(track.local_path)

            if candidate.is_file():
                return candidate

        folder = self.settings.work_path / "downloads" / track.username
        candidate = folder / (track.filename or virtual_basename(track.virtual_path))

        return candidate if candidate.is_file() else None

    def _launch(self, track, path: Path) -> None:

        key = track.id

        with self._lock:
            if key in self._running:
                return

            self._running.add(key)

        threading.Thread(target=self._process, args=(track, path), daemon=True,
                         name=f"digging-pipeline-{key}").start()

    def _set_status(self, track_id: str, **fields) -> None:

        crate = self._crate()
        track = None

        for entry in crate.tracks:
            if entry.id == track_id:
                for name, value in fields.items():
                    setattr(entry, name, value)

                track = entry
                break

        crate.save()

        if track is not None:
            events.emit("digging-status", track.id, **track_event_fields(track))

    # -- the work ---------------------------------------------------------

    def _process(self, track, path: Path) -> None:

        self._set_status(track.id, status=STATUS_SEPARATING)
        log.add(f"Digging: separating {path.name} ({self.settings.renderer})")

        try:
            separated = pipeline.separate(
                path, self.settings,
                progress=lambda message, fraction: log.add_debug(f"Digging: {message} ({fraction:.0%})"),
            )
            built = pipeline.build_set(
                separated, self.settings,
                name=f"{path.stem}",
                open_after=None,
            )

        except Exception as error:  # noqa: BLE001 - surface the reason in the crate
            log.add(f"Digging: separation failed for {path.name}: {error}")
            self._set_status(track.id, status=STATUS_FAILED, error=str(error))

        else:
            log.add(f"Digging: built {built.path.name} with {len(built.tracks)} stems")

            self._set_status(
                track.id,
                status=STATUS_SCHEDULED,
                bpm=built.bpm,
                stems={stem: str(stem_path) for stem, stem_path in separated.stems.items()},
                als_path=str(built.path),
            )

        finally:
            with self._lock:
                self._running.discard(track.id)


def track_event_fields(track) -> dict:
    """The slice of a crate track that changes as the pipeline runs."""

    return {
        "username": track.username,
        "filename": track.filename,
        "virtual_path": track.virtual_path,
        "status": track.status,
        "local_path": track.local_path,
        "bpm": track.bpm,
        "stems": dict(track.stems),
        "als_path": track.als_path,
        "error": track.error,
    }


SERVICE = PipelineService()


def start_service(settings: DiggingSettings | None = None) -> PipelineService:
    """Start the shared service once and return it."""

    if settings is not None:
        SERVICE.settings = settings

    SERVICE.start()
    return SERVICE
