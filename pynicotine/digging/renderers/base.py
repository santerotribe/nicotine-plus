# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared pieces for stem separation renderers."""

from __future__ import annotations

import re
import shutil
import zipfile

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from pynicotine.digging.settings import STEM_PRESETS

ProgressCallback = Callable[[str, float], None]

STEM_KEYWORDS = {
    "vocals": ("vocal", "vox", "voice", "speech"),
    "instrumental": ("instrumental", "inst", "karaoke", "no_vocals", "music"),
    "drums": ("drum", "percussion", "kick", "snare"),
    "bass": ("bass", "低音"),
    "guitar": ("guitar", "gtr"),
    "piano": ("piano", "keys"),
    "other": ("other", "residual", "accompaniment"),
}


class RenderError(Exception):
    pass


@dataclass
class RenderRequest:
    source: Path
    outdir: Path
    preset: str = "4"
    model: str = ""
    timeout: float = 3600.0

    def __post_init__(self) -> None:

        self.source = Path(self.source).expanduser()
        self.outdir = Path(self.outdir).expanduser()

        if self.preset not in STEM_PRESETS:
            raise RenderError(f"unknown stem preset: {self.preset}")

        if not self.source.is_file():
            raise RenderError(f"source file not found: {self.source}")


@dataclass
class RenderResult:
    stems: dict[str, Path] = field(default_factory=dict)
    renderer: str = ""
    job_id: str = ""
    files: list[Path] = field(default_factory=list)


class Renderer(Protocol):
    name: str

    def separate(self, request: RenderRequest, progress: ProgressCallback | None = None) -> RenderResult:
        ...


def _points() -> None:
    pass


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def guess_stem(filename: str) -> str:
    """Map a provider file name onto one of our stem names."""

    lowered = normalize_name(Path(filename).stem)

    for stem, keywords in STEM_KEYWORDS.items():
        for keyword in keywords:
            if keyword in lowered:
                return stem

    return "other"


def organize(files: list[Path], preset: str) -> dict[str, Path]:
    """Return a stem -> path mapping, keeping provider order stable."""

    wanted = STEM_PRESETS[preset]
    result: dict[str, Path] = {}
    leftovers: list[Path] = []

    for path in sorted(files):
        stem = guess_stem(path.name)

        if stem in wanted and stem not in result:
            result[stem] = path
        else:
            leftovers.append(path)

    # Fill gaps with remaining files so nothing is silently dropped
    for path in leftovers:
        for stem in wanted:
            if stem not in result:
                result[stem] = path
                break

    return {stem: path for stem, path in result.items() if stem in wanted}


def extract_archive(archive: Path, destination: Path) -> list[Path]:
    """Extract a zip returned by a provider and return the audio files inside."""

    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []

    with zipfile.ZipFile(archive) as handle:
        for member in handle.namelist():
            if member.endswith("/"):
                continue

            target = destination / Path(member).name
            with handle.open(member) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)

            extracted.append(target)

    return extracted


def audio_files_in(folder: Path) -> list[Path]:
    from pynicotine.digging.analyze import AUDIO_EXTENSIONS

    return sorted(
        path for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    )
