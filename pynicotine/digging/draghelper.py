# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Native macOS drag helper.

GTK4's outbound drag never landed a pasteboard item that Finder or Ableton
accepted, so we hand the file to AppKit directly: a tiny Swift helper shows a
floating chip which starts a real NSDraggingSession with a public.file-url.
Same mechanism Electron apps use (webContents.startDrag).
"""

from __future__ import annotations

import shutil
import subprocess

from pathlib import Path

from pynicotine.digging.settings import DiggingSettings

SOURCE = Path(__file__).parent / "resources" / "dragchip.swift"


def helper_binary(settings: DiggingSettings | None = None) -> Path | None:
    """Return the compiled helper, building it on first use (cached per profile)."""

    settings = settings or DiggingSettings.load()
    target = settings.work_path / "bin" / "dragchip"

    if target.is_file() and target.stat().st_mtime >= SOURCE.stat().st_mtime:
        return target

    compiler = shutil.which("swiftc") or shutil.which("swiftc", path="/usr/bin:/bin")

    if compiler is None:
        try:
            compiler = subprocess.run(
                ["xcrun", "--find", "swiftc"], capture_output=True, text=True, check=False, timeout=30
            ).stdout.strip() or None

        except (OSError, subprocess.SubprocessError):
            compiler = None

    if compiler is None:
        return None

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [compiler, "-O", "-o", str(target), str(SOURCE)],
            capture_output=True, timeout=300, check=False,
        )

    except (OSError, subprocess.SubprocessError):
        return None

    if completed.returncode != 0 or not target.is_file():
        return None

    return target


def start_drag(path: str | Path, settings: DiggingSettings | None = None) -> tuple[bool, str]:
    """Show the native drag chip for a file. Returns (started, reason)."""

    settings = settings or DiggingSettings.load()
    file_path = Path(path).expanduser()

    if not file_path.is_file():
        return False, "file is not on disk yet"

    binary = helper_binary(settings)

    if binary is None:
        return False, "swiftc is unavailable; install Xcode command line tools"

    try:
        subprocess.Popen(
            [str(binary), str(file_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    except OSError as error:
        return False, str(error)

    return True, ""
