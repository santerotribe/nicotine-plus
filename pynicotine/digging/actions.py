# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Glue between a browsed Soulseek file and the digging crate/pipeline."""

from __future__ import annotations

import shutil

from dataclasses import dataclass
from pathlib import Path

from pynicotine.digging.crate import STATUS_KEPT, Crate, CrateTrack
from pynicotine.digging.paths import virtual_basename
from pynicotine.digging.rolodex import Ledger
from pynicotine.digging.settings import DiggingSettings
from pynicotine.events import events
from pynicotine.logfacility import log
from pynicotine.transfers import TransferStatus


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
    updated = crate_for(settings).update(track.id, local_path=str(path))

    if updated is not None:
        track.local_path = str(path)
        _notify(updated)


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

    try:
        Ledger(settings.rolodex_path, settings.member_name, settings.member_id).add(
            source.username, source.virtual_path, source.folder_path,
            source.filename, kind,
        )

    except OSError as error:
        log.add("Digging: ledger write failed: %(error)s", {"error": error})

    download_folder = settings.work_path / "downloads" / source.username
    download_folder.mkdir(parents=True, exist_ok=True)

    # Our own share: the file is already on disk, no transfer is involved.
    if source.username == getattr(core.users, "login_username", ""):
        try:
            local = Path(core.shares.virtual2real(source.folder_path)) / source.filename

        except Exception:  # noqa: BLE001 - a share mapping failure must not break the keep
            local = None

        if local is not None and local.is_file():
            track.local_path = str(local)
            updated = crate.update(track.id, local_path=str(local), status=STATUS_KEPT)

            if updated is not None:
                _notify(updated)

            from pynicotine.digging.service import start_service

            start_service().kick(track)
            return track

    existing = core.downloads.transfers.get(source.username + source.virtual_path)
    kept_path = None

    if peer is not None and peer.username == source.username and peer.virtual_path == source.virtual_path:
        # A finished preview can be promoted; a running one cannot.
        kept_path = peer.promote(download_folder)

    if kept_path is None and existing is not None:
        finished_file = Path(existing.folder_path or "") / virtual_basename(source.virtual_path)

        if existing.status == TransferStatus.FINISHED and finished_file.is_file():
            target = download_folder / finished_file.name

            if not target.exists():
                shutil.copy2(finished_file, target)

            kept_path = target

        else:
            # The preview belongs to the audition, not to the keep: drop it and
            # queue a real download in the keep folder. Otherwise the transfer
            # is paused when the next audition starts and never arrives.
            try:
                core.downloads.abort_downloads({existing: None}, status=TransferStatus.CANCELLED)
                core.downloads.clear_downloads({existing: None})

            except Exception as error:  # noqa: BLE001 - keep the keep
                log.add_debug(f"Digging: could not reset preview transfer: {error}")

    if kept_path is not None:
        track.local_path = str(kept_path)
        updated = crate.update(track.id, local_path=str(kept_path), status=STATUS_KEPT)

        if updated is not None:
            _notify(updated)

        return track

    core.downloads.enqueue_download(
        source.username,
        virtual_path=source.virtual_path,
        folder_path=str(download_folder),
        size=source.size,
        file_attributes=source.attributes,
    )

    # An API-only session never visits the GTK page that starts the service;
    # without this, "separating when the download lands" is a lie there.
    from pynicotine.digging.service import start_service

    start_service()

    return track


def _notify(track: CrateTrack) -> None:

    from pynicotine.digging.service import track_event_fields

    events.emit("digging-status", track.id, **track_event_fields(track))
