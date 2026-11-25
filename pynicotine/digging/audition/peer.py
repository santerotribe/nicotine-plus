# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Peer preview: play the actual file a Soulseek user is sharing.

The catalogue is only a stand-in. When the peer is online we start a real
download in the background, and as soon as enough bytes exist we hand the
partial file to the player, so what you hear is the exact file you would keep.
Downloads land in the preview cache; keeping promotes a copy to the permanent
downloads folder.
"""

from __future__ import annotations

import shutil

from pathlib import Path

from pynicotine.events import events
from pynicotine.logfacility import log
from pynicotine.transfers import TransferStatus

FIRST_AUDIO_BYTES = 1024 * 1024        # ~1 MB is enough to start decoding
PARTIAL_PLAY_THRESHOLD = 384 * 1024    # don't bother below this


class PeerPreview:

    def __init__(self, username: str, virtual_path: str, filename: str, size: int,
                 attributes, cache_dir: Path) -> None:

        self.username = username
        self.virtual_path = virtual_path
        self.filename = filename
        self.size = int(size or 0)
        self.attributes = attributes
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.transfer = None
        self.partial_path = ""
        self.finished_path = ""
        self.status_text = "contacting peer"
        self.bytes = 0
        self.error = ""
        self.cancelled = False
        self.promote_to: Path | None = None

        self.on_update = None       # callable(preview) - called on every progress tick
        self.on_audio_ready = None  # callable(preview) - enough bytes to play
        self.on_promoted = None     # callable(path) - kept file copied to downloads

    # -- lifecycle --------------------------------------------------------

    def start(self, on_update=None, on_audio_ready=None) -> None:

        from pynicotine.core import core

        self.on_update = on_update
        self.on_audio_ready = on_audio_ready
        events.connect("update-download", self._on_transfer_update)

        existing = core.downloads.transfers.get(self.username + self.virtual_path)

        if existing is not None:
            self.transfer = existing
            finished = Path(existing.folder_path or "") / Path(self.virtual_path).name

            if existing.status == TransferStatus.FINISHED and finished.is_file():
                # Already downloaded: play it straight away, nothing to fetch
                self.finished_path = str(finished)
                self.partial_path = str(finished)
                self.status_text = "already downloaded"

                if self.on_audio_ready is not None:
                    self.on_audio_ready(self)

                return

            # A previous preview was paused when the listener moved on: resume it
            # rather than queueing a duplicate (enqueue_download would no-op).
            log.add(f"Digging: resuming paused peer preview {self.filename}")
            core.downloads.retry_download(existing, bypass_filter=True)
            return

        log.add(f"Digging: requesting {self.filename} from {self.username}")
        core.downloads.enqueue_download(
            self.username,
            virtual_path=self.virtual_path,
            folder_path=str(self.cache_dir),
            size=self.size,
            file_attributes=self.attributes,
        )

    def resume(self) -> None:
        """Ask the peer for more data after playback caught up with the buffer."""

        transfer = self.transfer

        if transfer is None or self.cancelled:
            return

        if transfer.status == TransferStatus.PAUSED:
            from pynicotine.core import core

            try:
                core.downloads.retry_download(transfer, bypass_filter=True)

            except Exception as error:  # noqa: BLE001
                log.add_debug(f"Digging: could not resume preview: {error}")

    def cancel(self) -> None:

        if self.cancelled:
            return

        self.cancelled = True

        try:
            events.disconnect("update-download", self._on_transfer_update)

        except (AttributeError, ValueError):
            pass

        if self.transfer is not None:
            from pynicotine.core import core

            try:
                core.downloads.abort_downloads({self.transfer: None}, TransferStatus.PAUSED)

            except Exception as error:  # noqa: BLE001
                log.add_debug(f"Digging: could not pause preview transfer: {error}")

    # -- events -----------------------------------------------------------

    def _on_transfer_update(self, transfer, _update_parent=None) -> None:

        if self.cancelled:
            return

        if transfer.username != self.username or transfer.virtual_path != self.virtual_path:
            return

        if transfer is not self.transfer:
            self.transfer = transfer
            log.add_debug(f"Digging: preview transfer started ({transfer.status})")

        self.bytes = int(transfer.current_byte_offset or 0)
        status = transfer.status or ""
        self.status_text = _status_text(status, transfer.queue_position)

        if status == TransferStatus.TRANSFERRING and self.size:
            self.status_text = f"downloading from peer ({self.bytes / 1e6:.1f}/{self.size / 1e6:.1f} MB)"

        handle = getattr(transfer, "file_handle", None)

        if handle is not None and self.bytes >= PARTIAL_PLAY_THRESHOLD:
            name = handle.name

            if isinstance(name, bytes):
                name = name.decode("utf-8", "replace")

            if name != self.partial_path and Path(name).is_file():
                self.partial_path = name

                if self.on_audio_ready is not None:
                    self.on_audio_ready(self)

        if status == TransferStatus.FINISHED:
            self.finished_path = str(Path(transfer.folder_path) / Path(self.virtual_path).name)

            if self.promote_to is not None:
                self._promote()

            if self.on_update is not None:
                self.on_update(self)

            self._cleanup_listener()
            return

        if status in {
            TransferStatus.USER_LOGGED_OFF,
            TransferStatus.CONNECTION_CLOSED,
            TransferStatus.CONNECTION_TIMEOUT,
            TransferStatus.DOWNLOAD_FOLDER_ERROR,
            TransferStatus.LOCAL_FILE_ERROR,
        }:
            self.error = self.status_text
            log.add(f"Digging: peer preview failed for {self.filename}: {status}")

        if self.on_update is not None:
            self.on_update(self)

    def _cleanup_listener(self) -> None:

        try:
            events.disconnect("update-download", self._on_transfer_update)

        except (AttributeError, ValueError):
            pass

    # -- keeping ----------------------------------------------------------

    def promote(self, target_dir: Path) -> Path | None:
        """Copy the finished file into the permanent downloads folder."""

        self.promote_to = Path(target_dir)
        self.promote_to.mkdir(parents=True, exist_ok=True)

        if self.finished_path and Path(self.finished_path).is_file():
            return self._promote()

        return None

    def _promote(self) -> Path | None:

        source = Path(self.finished_path)
        target = self.promote_to / source.name if self.promote_to else None

        if target is None or not source.is_file():
            return None

        if not target.exists():
            shutil.copy2(source, target)
            log.add(f"Digging: kept {source.name} -> {target}")

        self.promote_to = None

        if self.on_promoted is not None:
            self.on_promoted(target)

        return target


def _status_text(status: str, queue_position: int) -> str:

    if status == TransferStatus.QUEUED_PRIVILEGED:
        return f"queued (privileged) at #{queue_position}" if queue_position else "queued (privileged)"

    if status == TransferStatus.QUEUED_PRIORITIZED:
        return f"queued (prioritized) at #{queue_position}" if queue_position else "queued (prioritized)"

    if status == TransferStatus.QUEUED:
        return f"queued at #{queue_position}" if queue_position else "queued"

    if status == TransferStatus.GETTING_STATUS:
        return "asking peer for the file"

    if status == TransferStatus.TRANSFERRING:
        return "downloading from peer"

    return str(status or "contacting peer")
