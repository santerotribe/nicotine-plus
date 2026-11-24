# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Command line front end for the digging pipeline.

    python -m pynicotine.digging analyze track.mp3
    python -m pynicotine.digging run track.flac --preset 4 --renderer pc
    python -m pynicotine.digging build ./stems --bpm 92 --name "Night Drive"
"""

from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path

from pynicotine.digging import ableton, analyze, pipeline
from pynicotine.digging.crate import slugify
from pynicotine.digging.renderers.base import RenderError, audio_files_in
from pynicotine.digging.settings import DiggingSettings, STEM_PRESETS


def _progress(message: str, fraction: float) -> None:
    sys.stderr.write(f"[{fraction * 100:5.1f}%] {message}\n")
    sys.stderr.flush()


def _settings(args) -> DiggingSettings:
    settings = DiggingSettings.load()

    if getattr(args, "renderer", None):
        settings.renderer = args.renderer

    if getattr(args, "preset", None):
        settings.preset = args.preset

    if getattr(args, "model", None):
        settings.model = args.model

    if getattr(args, "token", None):
        settings.mvsep_token = args.token

    if getattr(args, "sep_type", None):
        settings.mvsep_sep_type = args.sep_type

    if getattr(args, "pc_url", None):
        settings.pc_url = args.pc_url

    return settings


def cmd_analyze(args) -> int:
    payload = analyze.describe(args.path)
    print(json.dumps(payload, indent=2))
    return 0


def cmd_types(_args) -> int:
    from pynicotine.digging.renderers.mvsep import list_algorithms

    for algorithm in list_algorithms():
        render_id = algorithm.get("render_id")
        name = algorithm.get("name")
        group = algorithm.get("algorithm_group_id")
        print(f"{render_id:>6}  {name}  (group {group})")

    return 0


def cmd_render(args) -> int:
    settings = _settings(args)
    separated = pipeline.separate(args.source, settings, preset=args.preset, progress=_progress)
    print(json.dumps({
        "source": str(separated.source),
        "renderer": separated.renderer,
        "bpm": separated.bpm,
        "bpm_confidence": separated.confidence,
        "duration": separated.duration,
        "preset": separated.preset,
        "stems": {stem: str(path) for stem, path in separated.stems.items()},
    }, indent=2))
    return 0


def cmd_build(args) -> int:
    settings = _settings(args)
    folder = Path(args.stems).expanduser()
    files = audio_files_in(folder)

    if not files:
        sys.stderr.write(f"no audio files in {folder}\n")
        return 2

    stems = {path.stem.lower(): path for path in files}
    session_name = args.name or folder.name
    built = ableton.build_live_set(
        stems=stems,
        out_dir=settings.output_path / slugify(session_name),
        name=session_name,
        bpm=args.bpm,
        settings=settings,
    )
    print(json.dumps({"set": str(built.path), "bpm": built.bpm, "warped": built.warped,
                      "tracks": list(built.tracks)}, indent=2))
    return 0


def cmd_run(args) -> int:
    settings = _settings(args)
    outcome = pipeline.run(
        args.source, settings, preset=args.preset, name=args.name,
        open_after=False if args.no_open else None, progress=_progress,
    )
    print(json.dumps(outcome, indent=2))
    return 0


def cmd_settings(args) -> int:
    settings = DiggingSettings.load()

    if args.action == "show":
        print(json.dumps({key: getattr(settings, key) for key in settings.__dataclass_fields__
                          if key != "extra"}, indent=2))
        return 0

    if not args.assignment:
        sys.stderr.write("usage: settings set key=value\n")
        return 2

    for assignment in args.assignment:
        key, _, value = assignment.partition("=")

        if not hasattr(settings, key):
            sys.stderr.write(f"unknown key: {key}\n")
            return 2

        current = getattr(settings, key)

        if isinstance(current, bool):
            value = value.lower() in {"1", "true", "yes", "on"}

        elif isinstance(current, int):
            value = int(value)

        setattr(settings, key, value)

    path = settings.save()
    print(json.dumps({"saved": str(path)}, indent=2))
    return 0


def cmd_agent(args) -> int:
    from pynicotine.digging import agent

    return agent.main([
        "--port", str(args.port),
        "--token", args.token or "",
        "--work-dir", args.work_dir,
    ])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m pynicotine.digging",
                                     description="Digging pipeline for the Nicotine+ fork")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="print metadata, tempo and duration")
    analyze_parser.add_argument("path")
    analyze_parser.set_defaults(func=cmd_analyze)

    types_parser = subparsers.add_parser("types", help="list MVSEP separation algorithms")
    types_parser.set_defaults(func=cmd_types)

    render_parser = subparsers.add_parser("render", help="separate one file into stems")
    render_parser.add_argument("source")
    render_parser.add_argument("--renderer", choices=("mvsep", "pc", "local"))
    render_parser.add_argument("--preset", choices=tuple(STEM_PRESETS))
    render_parser.add_argument("--model")
    render_parser.add_argument("--token")
    render_parser.add_argument("--sep-type", dest="sep_type")
    render_parser.add_argument("--pc-url", dest="pc_url")
    render_parser.set_defaults(func=cmd_render)

    build_parser_ = subparsers.add_parser("build", help="build a Live Set from a folder of stems")
    build_parser_.add_argument("stems")
    build_parser_.add_argument("--bpm", type=float, required=True)
    build_parser_.add_argument("--name")
    build_parser_.set_defaults(func=cmd_build)

    run_parser = subparsers.add_parser("run", help="separate and build a Live Set in one go")
    run_parser.add_argument("source")
    run_parser.add_argument("--renderer", choices=("mvsep", "pc", "local"))
    run_parser.add_argument("--preset", choices=tuple(STEM_PRESETS))
    run_parser.add_argument("--model")
    run_parser.add_argument("--token")
    run_parser.add_argument("--sep-type", dest="sep_type")
    run_parser.add_argument("--pc-url", dest="pc_url")
    run_parser.add_argument("--name")
    run_parser.add_argument("--no-open", action="store_true")
    run_parser.set_defaults(func=cmd_run)

    settings_parser = subparsers.add_parser("settings", help="show or change digging settings")
    settings_parser.add_argument("action", choices=("show", "set"))
    settings_parser.add_argument("assignment", nargs="*")
    settings_parser.set_defaults(func=cmd_settings)

    agent_parser = subparsers.add_parser("agent", help="run the studio PC separation agent")
    agent_parser.add_argument("--port", type=int, default=8765)
    agent_parser.add_argument("--token")
    agent_parser.add_argument("--work-dir", default=str(Path.home() / "NicotineStems"))
    agent_parser.set_defaults(func=cmd_agent)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return int(args.func(args) or 0)

    except (pipeline.PipelineError, ableton.AbletonError, RenderError, analyze.AnalysisError) as error:
        sys.stderr.write(f"error: {error}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
