# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Local Demucs separation backend (runs on this machine)."""

from __future__ import annotations

import shutil
import subprocess
import sys

from pathlib import Path

from pynicotine.digging.renderers.base import (
    ProgressCallback,
    RenderError,
    RenderRequest,
    RenderResult,
    audio_files_in,
    organize,
)

DEFAULT_MODEL = "htdemucs"


def available() -> bool:
    return shutil.which("demucs") is not None or _module_available()


def _module_available() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("demucs") is not None

    except (ImportError, ValueError):
        return False


class LocalDemucsRenderer:
    name = "local"

    def __init__(self, model: str = "", device: str = "") -> None:
        self.model = model or DEFAULT_MODEL
        self.device = device

    def separate(self, request: RenderRequest, progress: ProgressCallback | None = None) -> RenderResult:

        executable = shutil.which("demucs")
        command: list[str]

        if executable:
            command = [executable]

        elif _module_available():
            command = [sys.executable, "-m", "demucs"]

        else:
            raise RenderError("Demucs is not installed (pip install demucs, or use the mvsep/pc renderer)")

        if request.preset == "2":
            command += ["--two-stems", "vocals"]

        command += ["-n", request.model or self.model]

        if self.device:
            command += ["-d", self.device]

        outdir = request.outdir
        outdir.mkdir(parents=True, exist_ok=True)
        command += ["-o", str(outdir), str(request.source)]

        if progress:
            progress("running demucs", 0.1)

        completed = subprocess.run(command, capture_output=True, text=True, timeout=request.timeout)

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip().splitlines()[-3:]
            raise RenderError("demucs failed: " + " | ".join(detail))

        files = audio_files_in(outdir)
        stems = organize(files, request.preset)

        if not stems:
            raise RenderError("demucs produced no output")

        return RenderResult(stems=stems, renderer=self.name, files=files)
