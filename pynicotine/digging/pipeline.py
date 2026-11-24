# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Digging pipeline: one track in, stems and a Live Set out."""

from __future__ import annotations

import shutil

from dataclasses import dataclass, field
from pathlib import Path

from pynicotine.digging import ableton, analyze
from pynicotine.digging.crate import slugify
from pynicotine.digging.renderers import RenderRequest, get_renderer
from pynicotine.digging.settings import DiggingSettings


@dataclass
class Separated:
    source: Path
    stems: dict[str, Path] = field(default_factory=dict)
    bpm: float = 0.0
    confidence: float = 0.0
    duration: float = 0.0
    preset: str = "4"
    renderer: str = ""


class PipelineError(Exception):
    pass


def _report(progress, message: str, fraction: float) -> None:
    if progress:
        progress(message, max(0.0, min(1.0, fraction)))


def separate(source: str | Path, settings: DiggingSettings, preset: str | None = None,
             progress=None) -> Separated:
    """Run the configured renderer over one file and return the stems."""

    source_path = Path(source).expanduser()

    if not source_path.is_file():
        raise PipelineError(f"file not found: {source_path}")

    settings.ensure_dirs()
    info = analyze.describe(source_path)
    chosen_preset = preset or settings.preset
    target = settings.work_path / "stems" / slugify(source_path.stem)

    if target.exists():
        shutil.rmtree(target, ignore_errors=True)

    renderer = get_renderer(settings)
    request = RenderRequest(
        source=source_path,
        outdir=target,
        preset=chosen_preset,
        model=settings.model,
    )

    _report(progress, f"separating with {renderer.name}", 0.05)
    result = renderer.separate(request, progress=progress)

    bpm = float(info.get("bpm") or 0.0)
    confidence = float(info.get("bpm_confidence") or 0.0)

    # Keep the source next to the stems so the session is self-contained
    copied_source = target / source_path.name

    if not copied_source.exists():
        shutil.copy2(source_path, copied_source)

    return Separated(
        source=source_path,
        stems={stem: Path(path) for stem, path in result.stems.items()},
        bpm=bpm,
        confidence=confidence,
        duration=float(info.get("duration") or 0.0),
        preset=chosen_preset,
        renderer=result.renderer,
    )


def build_set(separated: Separated, settings: DiggingSettings, name: str | None = None,
              open_after: bool | None = None) -> ableton.BuiltSet:
    """Build (and optionally open) a Live Set from separated stems."""

    if not separated.stems:
        raise PipelineError("nothing separated yet")

    bpm = separated.bpm or 120.0
    session_name = name or f"{separated.source.stem} {int(round(bpm))}BPM"
    out_dir = settings.output_path / slugify(session_name)
    built = ableton.build_live_set(
        stems=separated.stems,
        out_dir=out_dir,
        name=session_name,
        bpm=bpm,
        settings=settings,
    )

    should_open = settings.open_after_build if open_after is None else open_after

    if should_open:
        ableton.open_in_live(built.path, settings)

    return built


def run(source: str | Path, settings: DiggingSettings, preset: str | None = None,
        name: str | None = None, open_after: bool | None = None, progress=None) -> dict:
    """Full flow: analyse, separate, assemble the Live Set, open it."""

    separated = separate(source, settings, preset=preset, progress=progress)
    built = build_set(separated, settings, name=name, open_after=open_after)

    return {
        "source": str(separated.source),
        "renderer": separated.renderer,
        "bpm": separated.bpm,
        "bpm_confidence": separated.confidence,
        "stems": {stem: str(path) for stem, path in separated.stems.items()},
        "set": str(built.path),
        "warped": built.warped,
    }
