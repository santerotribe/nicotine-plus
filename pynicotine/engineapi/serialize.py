# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""JSON shapes for the engine API.

The contract is deliberately raw: names and numbers, no pre-formatted strings,
so a native front end can format for its own platform.
"""

from __future__ import annotations

from pathlib import Path


def file_dict(file_data) -> dict:
    attributes = getattr(file_data, "attributes", None)
    return {
        "name": file_data.path,
        "size": int(file_data.size or 0),
        "bitrate": getattr(attributes, "bitrate", None),
        "length": getattr(attributes, "length", None),
        "vbr": getattr(attributes, "vbr", None),
        "sample_rate": getattr(attributes, "sample_rate", None),
        "bit_depth": getattr(attributes, "bit_depth", None),
    }


def transfer_dict(transfer) -> dict:
    return {
        "username": transfer.username,
        "virtual_path": transfer.virtual_path,
        "filename": transfer.virtual_path.replace("\\", "/").rsplit("/", 1)[-1],
        "folder": transfer.folder_path,
        "size": int(transfer.size or 0),
        "transferred": int(transfer.current_byte_offset or 0),
        "status": str(transfer.status or ""),
        "queue_position": int(transfer.queue_position or 0),
        "speed": float(getattr(transfer, "speed", 0) or 0),
        "percent": round(
            (float(transfer.current_byte_offset or 0) / float(transfer.size)) * 100, 1
        ) if transfer.size else 0.0,
    }


def crate_track_dict(track) -> dict:
    return {
        "id": track.id,
        "username": track.username,
        "filename": track.filename,
        "virtual_path": track.virtual_path,
        "kind": track.kind,
        "status": track.status,
        "bpm": track.bpm,
        "local_path": track.local_path,
        "stems": dict(track.stems),
        "als_path": track.als_path,
        "error": track.error,
        "added_at": track.added,
    }


def path_dict(path) -> dict:
    return {"path": str(Path(path))}
