# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Digging pipeline: Soulseek browser -> audition -> download -> stems -> Ableton.

The modules here are UI-agnostic so they can be driven from the GTK client, a
CLI, or a headless service:

- analyze.py    ffprobe/ffmpeg metadata, waveform peaks and tempo detection
- crate.py      the persisted list of candidate and kept tracks
- renderers/    stem separation backends (MVSEP, studio PC agent, local Demucs)
- ableton.py    Live Set (.als) generation and launching through ALS Observatory
- pipeline.py   the state machine tying the steps together
"""

from pynicotine.digging.settings import DiggingSettings

__all__ = ["DiggingSettings"]
