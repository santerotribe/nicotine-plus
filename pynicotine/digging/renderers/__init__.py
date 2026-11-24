# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Stem separation backends."""

from __future__ import annotations

from pynicotine.digging.renderers.base import (
    RenderError,
    RenderRequest,
    RenderResult,
    Renderer,
    organize,
)

__all__ = ["RenderError", "RenderRequest", "RenderResult", "Renderer", "organize", "get_renderer"]


def get_renderer(settings) -> Renderer:
    """Build the renderer selected in settings."""

    choice = (settings.renderer or "mvsep").lower()

    if choice == "mvsep":
        from pynicotine.digging.renderers.mvsep import MvsepRenderer

        return MvsepRenderer(
            token=settings.mvsep_token,
            sep_type=settings.mvsep_sep_type,
            poll_seconds=settings.mvsep_poll_seconds,
        )

    if choice == "pc":
        from pynicotine.digging.renderers.pc_agent import PcAgentRenderer

        return PcAgentRenderer(base_url=settings.pc_url, token=settings.pc_token)

    if choice == "local":
        from pynicotine.digging.renderers.local import LocalDemucsRenderer

        return LocalDemucsRenderer(model=settings.model)

    raise RenderError(f"unknown renderer: {settings.renderer!r}")
