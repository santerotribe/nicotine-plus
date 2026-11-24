# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Ableton Live Set generation.

We do not hand-write track XML: the actual .als is produced by ALS Observatory
(schema-v2 audio clip templates cut from Live-saved sets), and this module adds
the finishing touches our workflow needs -- one audio track per stem, project
tempo matched to the sampled record, and clips switched to warped so the stems
stay in time when the set tempo changes.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from dataclasses import dataclass
from pathlib import Path

from pynicotine.digging.analyze import probe

WARP_MODES = {
    "beats": 0,
    "tones": 1,
    "texture": 2,
    "repitch": 3,
    "complex": 4,
    "complex_pro": 5,
}

# Per-stem warp defaults: transient material keeps its punch, tonal material
# uses Complex Pro to avoid artifacts when the tempo moves.
STEM_WARP_MODES = {
    "drums": "beats",
    "percussion": "beats",
    "bass": "tones",
    "vocals": "complex_pro",
    "instrumental": "complex_pro",
    "guitar": "complex_pro",
    "piano": "complex_pro",
    "other": "complex_pro",
}

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class AbletonError(Exception):
    pass


@dataclass
class BuiltSet:
    path: Path
    bpm: float
    tracks: tuple[str, ...]
    warped: bool


def _observatory_python(root: Path) -> list[str]:
    """Command prefix that can run als_observatory for a given checkout."""

    venv_python = root / ".venv" / "bin" / "python"

    if venv_python.is_file():
        return [str(venv_python)]

    return [sys.executable]


def _template(settings) -> Path:
    if settings.live_template:
        candidate = Path(settings.live_template).expanduser()

        if candidate.is_file():
            return candidate

    app = Path(settings.live_app).expanduser()
    candidate = app / "Contents" / "App-Resources" / "Builtin" / "Templates" / "DefaultLiveSet.als"

    if candidate.is_file():
        return candidate

    raise AbletonError(
        "No Live template found. Set 'live_template' to a saved empty .als "
        "(Live: File > Save Live Set As) or point 'live_app' at Ableton Live."
    )


def _sanitize(value: str, fallback: str = "Digging") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")

    if not cleaned or not cleaned[0].isalnum():
        cleaned = fallback

    return cleaned[:100]


def _asset_id(stem: str, index: int) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-") or "stem"
    return f"s{index}-{token}"


def _observe(settings, spec_path: Path, out_dir: Path) -> Path:
    root = Path(settings.observatory_root).expanduser()

    if not (root / "src" / "als_observatory").is_dir():
        raise AbletonError(f"ALS Observatory not found at {root}")

    template = _template(settings)
    environment = dict(os.environ)
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = f"{root / 'src'}{os.pathsep}{existing}" if existing else str(root / "src")

    command = [
        *_observatory_python(root), "-m", "als_observatory", "generate", "build",
        str(spec_path), "--template", str(template),
    ]

    completed = subprocess.run(
        command, cwd=str(out_dir), capture_output=True, text=True,
        timeout=600, env=environment,
    )

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-800:]
        raise AbletonError(f"ALS Observatory failed: {detail}")

    payload = {}

    for line in reversed(completed.stdout.splitlines()):
        line = line.strip()

        if line.startswith("{") and line.endswith("}"):
            try:
                payload = json.loads(line)
                break

            except ValueError:
                continue

    artifact = payload.get("artifact")

    if not artifact:
        raise AbletonError(f"ALS Observatory produced no artifact: {completed.stdout[-400:]}")

    candidates = [
        out_dir / artifact,
        out_dir / ".als-observatory" / artifact,
    ]
    path = next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)

    if path is None:
        matches = sorted(out_dir.rglob(Path(artifact).name))
        path = matches[0].resolve() if matches else None

    if path is None:
        raise AbletonError(f"generated set is missing: {out_dir / artifact}")

    return path


def _warp_markers(clip_xml: str, bpm: float, index: int = 0) -> str:
    """Write two tempo-defining warp markers for a clip at the given tempo."""

    beat_seconds = 60.0 / bpm
    first_id = 40000 + (index * 2)

    markers = (
        '<WarpMarkers>'
        f'<WarpMarker Id="{first_id}" SecTime="0" BeatTime="0" />'
        f'<WarpMarker Id="{first_id + 1}" SecTime="{beat_seconds:.9f}" BeatTime="1" />'
        "</WarpMarkers>"
    )

    replaced, count = re.subn(r"<WarpMarkers\s*/>", markers, clip_xml, count=1)

    if not count:
        replaced, count = re.subn(r"<WarpMarkers>.*?</WarpMarkers>", markers, clip_xml, count=1, flags=re.S)

    if not count:
        if "<WarpMode" in clip_xml:
            replaced = clip_xml.replace("<WarpMode", markers + "<WarpMode", 1)
        else:
            replaced = clip_xml.replace("</AudioClip>", markers + "</AudioClip>", 1)

    return replaced


def _collect_samples(xml: str, out_dir: Path, stems: dict[str, Path]) -> str:
    """Copy stems into the set's Samples/Collected folder and repoint the clips.

    ALS Observatory writes a RelativePath of Samples/Collected/<file> but leaves
    media in place, so Live reports every sample as missing. Collecting them
    makes the set self-contained and portable.
    """

    collected = out_dir / "Samples" / "Collected"
    collected.mkdir(parents=True, exist_ok=True)
    sources = {path.name: path for path in stems.values() if Path(path).is_file()}

    def _repoint(match: re.Match) -> str:
        block = match.group(0)
        path_match = re.search(r'<Path Value="([^"]*)" />', block)

        if not path_match:
            return block

        original = Path(path_match.group(1))
        source = sources.get(original.name)

        if source is None:
            return block

        target = collected / source.name

        if source.resolve() != target.resolve():
            shutil.copy2(source, target)

        block = block.replace(
            f'<Path Value="{path_match.group(1)}" />',
            f'<Path Value="{target.resolve()}" />',
        )
        # RelativePathType 3 (project-relative) is not honoured on load here:
        # Live reports the collected sample as unopenable. Absolute references
        # load reliably; "Collect All and Save" restores portability later.
        block = re.sub(r'<RelativePathType Value="\d+" />', '<RelativePathType Value="0" />', block, count=1)
        block = re.sub(r'<RelativePath Value="[^"]*" />', '<RelativePath Value="" />', block, count=1)
        block = re.sub(
            r'<OriginalFileSize Value="\d+" />',
            f'<OriginalFileSize Value="{target.stat().st_size}" />',
            block,
            count=1,
        )
        return block

    return re.sub(r"<FileRef>.*?</FileRef>", _repoint, xml, flags=re.S)


def _rewrite_warp(als_path: Path, bpm: float, stem_modes: dict[str, str],
                  out_dir: Path | None = None, stems: dict[str, Path] | None = None,
                  warp: bool = True) -> None:
    """Enable warping on every generated clip and write correct warp markers."""

    raw = gzip.decompress(als_path.read_bytes())
    xml = raw.decode("utf-8")

    if out_dir is not None and stems:
        xml = _collect_samples(xml, out_dir, stems)

    clips = re.findall(r"<AudioClip\b.*?</AudioClip>", xml, flags=re.S)

    if warp and not clips:
        raise AbletonError("generated set contains no audio clips to warp")

    order = list(stem_modes.keys())

    for index, clip in enumerate(clips if warp else []):
        stem = order[index] if index < len(order) else "other"
        mode = WARP_MODES.get(stem_modes.get(stem, "complex_pro"), 5)

        updated = clip.replace('<IsWarped Value="false" />', '<IsWarped Value="true" />', 1)
        updated = re.sub(r'<WarpMode Value="\d+" />', f'<WarpMode Value="{mode}" />', updated, count=1)
        updated = _warp_markers(updated, bpm, index=index)
        xml = xml.replace(clip, updated, 1)

    data = xml.encode("utf-8")

    with tempfile.NamedTemporaryFile(dir=als_path.parent, suffix=".als", delete=False) as handle:
        temp_path = Path(handle.name)

    try:
        with gzip.GzipFile(filename="", mode="wb", fileobj=temp_path.open("wb"), mtime=0) as gz:
            gz.write(data)

        shutil.move(str(temp_path), str(als_path))

    finally:
        temp_path.unlink(missing_ok=True)


def build_live_set(stems: dict[str, Path], out_dir: Path, name: str, bpm: float,
                   settings, warp: bool | None = None) -> BuiltSet:
    """Create a Live Set with one audio track per stem and return its path."""

    if not stems:
        raise AbletonError("no stems to build a set from")

    if not bpm or bpm <= 0:
        raise AbletonError("a valid tempo is required to build a set")

    out_dir = Path(out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    # A fresh run directory per build: ALS Observatory never overwrites output
    run_dir = out_dir / ".observatory-run" / f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
    run_dir.mkdir(parents=True, exist_ok=True)

    display = _sanitize(name, "Digging")
    filename = _sanitize(name, "Digging Session")

    assets = []
    tracks = []
    stem_modes: dict[str, str] = {}

    for index, (stem, path) in enumerate(stems.items()):
        info = probe(path)
        asset = _asset_id(stem, index)
        assets.append({"id": asset, "path": str(Path(path).resolve())})
        tracks.append({
            "id": f"t{index}-{_sanitize(stem, 'stem').lower()}",
            "type": "audio",
            "name": stem.upper()[:120],
            "color": (index * 7) % 70,
            "clips": [{
                "id": f"c{index}",
                "asset": asset,
                "name": Path(path).name,
                "start_beats": 0,
            }],
        })
        stem_modes[stem] = STEM_WARP_MODES.get(stem.lower(), "complex_pro")
        _ = info

    spec = {
        "schema_version": 2,
        "name": display,
        "filename": filename,
        "tempo_bpm": round(float(bpm), 3),
        "loop": {"start_beats": 0, "length_beats": 16, "enabled": True},
        "assets": assets,
        "tracks": tracks,
    }

    spec_path = run_dir / "spec.json"
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    built = _observe(settings, spec_path, run_dir)

    # Keep a stable, predictable path for the finished set
    final_path = out_dir / f"{filename}.als"

    if built.resolve() != final_path.resolve():
        shutil.copy2(built, final_path)

    built = final_path

    should_warp = settings.warp_stems if warp is None else warp
    stem_modes = {stem: (_warp_mode_for(stem, settings) if not should_warp else stem_modes.get(stem, "complex_pro"))
                  for stem in stems}

    _rewrite_warp(built, float(bpm), stem_modes if should_warp else {}, out_dir=out_dir,
                  stems=stems, warp=should_warp)

    return BuiltSet(path=built, bpm=float(bpm), tracks=tuple(stems), warped=bool(should_warp))


def _warp_mode_for(stem: str, settings) -> str:
    configured = (settings.warp_mode or "").strip().lower()

    if configured in WARP_MODES and configured != "complex":
        return configured

    return STEM_WARP_MODES.get(stem.lower(), "complex_pro")


def open_in_live(als_path: Path, settings) -> bool:
    """Open the generated set in Ableton Live. Returns False when unavailable."""

    path = Path(als_path).expanduser()

    if not path.is_file():
        raise AbletonError(f"set not found: {path}")

    if sys.platform == "darwin":
        app = Path(settings.live_app).expanduser()

        if app.is_dir():
            completed = subprocess.run(["open", "-a", str(app), str(path)], check=False)
            return completed.returncode == 0

    completed = subprocess.run(["open", str(path)], check=False)
    return completed.returncode == 0
