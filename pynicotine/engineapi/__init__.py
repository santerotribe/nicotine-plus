# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Local HTTP API exposing the client engine to a native front end."""

from pynicotine.engineapi.server import maybe_start, start

__all__ = ["start", "maybe_start"]
