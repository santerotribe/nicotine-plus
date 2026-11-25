# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Housekeeping for the disposable side of digging.

Preview transfers are paused when the listener moves on, and exported WAVs pile
up as you audition. None of that should outlive its usefulness, so on startup we:

- cancel and forget paused preview transfers that were never kept
- delete preview files no live transfer references
- trim both preview and export caches to their budgets
"""

from __future__ import annotations

import shutil

from dataclasses import dataclass
from pathlib import Path

from pynicotine.digging.cache import PreviewCache
from pynicotine.digging.paths import virtual_basename
from pynicotine.digging.settings import DiggingSettings
from pynicotine.transfers import TransferStatus


@dataclass
class SweepReport:
    transfers_removed: int = 0
    files_removed: int = 0
    bytes_freed: int = 0
    cache_evicted: int = 0

    def as_dict(self) -> dict:
        return {
            "transfers_removed": self.transfers_removed,
            "files_removed": self.files_removed,
            "freed_mb": round(self.bytes_freed / (1024 * 1024), 1),
            "cache_evicted": self.cache_evicted,
        }


def sweep(settings: DiggingSettings | None = None, core=None) -> SweepReport:
    """Clear abandoned preview state. Safe to call when no client is running."""

    settings = settings or DiggingSettings.load()
    previews = settings.work_path / "previews"
    exports = settings.export_path.expanduser()
    report = SweepReport()

    kept_paths: set[str] = set()

    if core is not None:
        from pynicotine.digging.actions import crate_for

        try:
            kept_paths = {track.virtual_path for track in crate_for(settings)}

        except OSError:
            kept_paths = set()

        for transfer in list(core.downloads.transfers.values()):
            folder = Path(transfer.folder_path or "")

            if folder != previews:
                continue

            if transfer.virtual_path in kept_paths:
                # Explicitly kept: let it finish
                continue

            try:
                if transfer.status != TransferStatus.FINISHED:
                    core.downloads.abort_downloads({transfer: None}, status=TransferStatus.CANCELLED)

                core.downloads.clear_downloads({transfer: None})

            except Exception:  # noqa: BLE001 - housekeeping must never block startup
                continue

            report.transfers_removed += 1

    # Files still referenced by a live transfer stay. A transfer writes into an
    # INCOMPLETE<md5> file, so both names must be protected.
    active_names: set[str] = set()

    if core is not None:
        for transfer in core.downloads.transfers.values():
            if Path(transfer.folder_path or "") != previews:
                continue

            active_names.add(virtual_basename(transfer.virtual_path))
            handle = getattr(transfer, "file_handle", None)

            if handle is not None:
                name = handle.name

                if isinstance(name, bytes):
                    name = name.decode("utf-8", "replace")

                active_names.add(Path(name).name)

    import time as _time

    recent = _time.time() - 300

    if previews.is_dir():
        for path in previews.rglob("*"):
            try:
                if not path.is_file() or path.name in active_names:
                    continue

                if path.name.startswith("INCOMPLETE") or path.stat().st_mtime > recent:
                    continue

                size = path.stat().st_size
                path.unlink()
                report.files_removed += 1
                report.bytes_freed += size

            except OSError:
                continue

    for folder, limit in ((previews, settings.preview_cache_bytes), (exports, settings.preview_cache_bytes)):
        try:
            evicted = PreviewCache(folder, limit).enforce()
            report.cache_evicted += evicted.removed

        except OSError:
            continue

    return report


def wipe(settings: DiggingSettings | None = None) -> SweepReport:
    """Remove every disposable file (previews and exports)."""

    settings = settings or DiggingSettings.load()
    report = SweepReport()

    for folder in (settings.work_path / "previews", settings.export_path.expanduser()):
        if not folder.is_dir():
            continue

        for path in folder.rglob("*"):
            try:
                if not path.is_file():
                    continue

                size = path.stat().st_size
                path.unlink()
                report.files_removed += 1
                report.bytes_freed += size

            except OSError:
                continue

        shutil.rmtree(folder, ignore_errors=True)

    return report
