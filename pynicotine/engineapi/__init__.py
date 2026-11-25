# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Local HTTP API exposing the client engine to a native front end."""

from pynicotine.engineapi.hub import event_hub
from pynicotine.engineapi.server import maybe_start, start, stop

__all__ = ["event_hub", "maybe_start", "start", "stop"]
