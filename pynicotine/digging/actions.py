# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Glue between a browsed Soulseek file and the digging crate/pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from pynicotine.digging.crate import STATUS_KEPT, Crate, CrateTrack
from pynicotine.digging.settings import DiggingSettings
from pynicotine.events import events


@dataclass
class TrackSource:
    username: str
    folder_path: str
    filename: str
    size: int = 0
    attributes: object = None

    @property
    def virtual_path(self) -> str:
        return "\\".join([self.folder_path, self.filename])


def record_local_path(track: CrateTrack, path: str,
                      settings: DiggingSettings | None = None) -> None:

    settings = settings or DiggingSettings.load()
    crate = crate_for(settings)
    track.local_path = str(path)

    for entry in crate.tracks:
        if entry.id == track.id:
            entry.local_path = str(path)

    crate.save()
    _notify(track)


def crate_for(settings: DiggingSettings | None = None) -> Crate:
    settings = settings or DiggingSettings.load()
    settings.ensure_dirs()
    return Crate(settings.work_path / "crate.json")


def keep_source(core, source: TrackSource, settings: DiggingSettings | None = None,
                peer=None, kind: str = "sample") -> CrateTrack:
    """Add a browsed file to the crate and make sure the real file is kept."""

    settings = settings or DiggingSettings.load()
    settings.ensure_dirs()

    crate = crate_for(settings)
    track = crate.add(CrateTrack(
        username=source.username,
        virtual_path=source.virtual_path,
        filename=source.filename,
        size=source.size,
        kind=kind,
    ))
    track.status = STATUS_KEPT
    crate.save()
    _notify(track)

    download_folder = settings.work_path / "downloads" / source.username
    download_folder.mkdir(parents=True, exist_ok=True)

    if peer is not None and peer.username == source.username and peer.virtual_path == source.virtual_path:
        # A preview download is already in flight: promote it when it finishes
        kept_path = peer.promote(download_folder)

        if kept_path is not None:
            track.local_path = str(kept_path)

        crate.save()
        return track

    core.downloads.enqueue_download(
        source.username,
        virtual_path=source.virtual_path,
        folder_path=str(download_folder),
        size=source.size,
        file_attributes=source.attributes,
    )

    return track


def _notify(track: CrateTrack) -> None:

    from pynicotine.digging.service import track_event_fields

    events.emit("digging-status", track.id, **track_event_fields(track))
