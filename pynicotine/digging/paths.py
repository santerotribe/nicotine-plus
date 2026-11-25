# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Path helpers for Soulseek virtual paths (backslash separated)."""

from __future__ import annotations


def virtual_basename(virtual_path: str) -> str:
    """Return the file name of a virtual path, whatever the separator."""

    return virtual_path.replace("\\", "/").rsplit("/", 1)[-1]


def virtual_folder(virtual_path: str) -> str:
    """Return the folder part of a virtual path (empty when at the root)."""

    normalized = virtual_path.replace("\\", "/")

    if "/" not in normalized:
        return ""

    return normalized.rsplit("/", 1)[0]
