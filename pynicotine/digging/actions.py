# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Glue between a browsed Soulseek file and the digging crate/pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from pynicotine.digging.crate import STATUS_KEPT, Crate, CrateTrack
from pynicotine.digging.settings import DiggingSettings


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


def crate_for(settings: DiggingSettings | None = None) -> Crate:
    settings = settings or DiggingSettings.load()
    settings.ensure_dirs()
    return Crate(settings.work_path / "crate.json")


def keep_source(core, source: TrackSource, settings: DiggingSettings | None = None) -> CrateTrack:
    """Add a browsed file to the crate and start downloading it."""

    settings = settings or DiggingSettings.load()
    settings.ensure_dirs()

    crate = crate_for(settings)
    track = crate.add(CrateTrack(
        username=source.username,
        virtual_path=source.virtual_path,
        filename=source.filename,
        size=source.size,
    ))
    track.status = STATUS_KEPT
    crate.save()

    download_folder = settings.work_path / "downloads" / source.username
    download_folder.mkdir(parents=True, exist_ok=True)

    core.downloads.enqueue_download(
        source.username,
        virtual_path=source.virtual_path,
        folder_path=str(download_folder),
        size=source.size,
        file_attributes=source.attributes,
    )

    return track
