# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Preview cache: bounded disk use for audio nobody asked to keep.

Auditioning a lot of tracks leaves exported WAVs and (later) partial peer
downloads behind. Anything in the cache is disposable: keeping a track copies it
into the downloads folder first, so eviction can never touch kept material.
"""

from __future__ import annotations

import shutil

from dataclasses import dataclass
from pathlib import Path


@dataclass
class CacheReport:
    removed: int = 0
    freed_bytes: int = 0
    total_bytes: int = 0
    files: int = 0

    @property
    def freed_mb(self) -> float:
        return round(self.freed_bytes / (1024 * 1024), 1)

    @property
    def total_mb(self) -> float:
        return round(self.total_bytes / (1024 * 1024), 1)


class PreviewCache:

    def __init__(self, root: Path, max_bytes: int = 2 * 1024 * 1024 * 1024) -> None:
        self.root = Path(root)
        self.max_bytes = max(0, int(max_bytes))

    def entries(self) -> list[tuple[float, int, Path]]:
        """(mtime, size, path) for every cached file, oldest first."""

        if not self.root.is_dir():
            return []

        found = []

        for path in self.root.rglob("*"):
            try:
                if not path.is_file():
                    continue

                stat = path.stat()

            except OSError:
                continue

            found.append((stat.st_mtime, stat.st_size, path))

        found.sort(key=lambda item: item[0])
        return found

    def usage(self) -> CacheReport:
        entries = self.entries()
        return CacheReport(
            removed=0,
            freed_bytes=0,
            total_bytes=sum(size for _mtime, size, _path in entries),
            files=len(entries),
        )

    def enforce(self) -> CacheReport:
        """Delete oldest files until the cache is under its size limit."""

        entries = self.entries()
        total = sum(size for _mtime, size, _path in entries)
        removed = 0
        freed = 0

        for _mtime, size, path in entries:
            if total <= self.max_bytes:
                break

            try:
                path.unlink()

            except OSError:
                continue

            total -= size
            freed += size
            removed += 1

        return CacheReport(removed=removed, freed_bytes=freed, total_bytes=total,
                           files=max(0, len(entries) - removed))

    def clear(self) -> CacheReport:
        entries = self.entries()
        freed = 0
        removed = 0

        for _mtime, size, path in entries:
            try:
                path.unlink()

            except OSError:
                continue

            freed += size
            removed += 1

        # Remove now-empty directories
        if self.root.is_dir():
            for folder in sorted(self.root.rglob("*"), reverse=True):
                if folder.is_dir() and not any(folder.iterdir()):
                    shutil.rmtree(folder, ignore_errors=True)

        return CacheReport(removed=removed, freed_bytes=freed, total_bytes=0, files=0)
