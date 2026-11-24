# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Settings for the digging pipeline, stored next to the Nicotine+ config."""

from __future__ import annotations

import json
import os

from dataclasses import asdict, dataclass, field
from pathlib import Path

STEM_PRESETS = {
    "2": ("vocals", "instrumental"),
    "4": ("vocals", "drums", "bass", "other"),
    "6": ("vocals", "drums", "bass", "guitar", "piano", "other"),
}


def default_config_dir() -> Path:
    """Return the Nicotine+ config directory, respecting XDG and portable installs."""

    xdg = os.environ.get("XDG_CONFIG_HOME")

    if xdg:
        return Path(xdg) / "nicotine"

    return Path.home() / ".config" / "nicotine"


def default_observatory_root() -> Path:
    return Path.home() / "Documents" / "ALS Observatory"


def default_live_app() -> Path:
    return Path("/Applications/Ableton Live 12 Suite.app")


@dataclass
class DiggingSettings:

    # Where the pipeline keeps downloads, stems and generated Live sets
    work_dir: str = ""
    output_dir: str = ""

    # Stem separation
    renderer: str = "mvsep"             # mvsep | pc | local
    preset: str = "4"                   # see STEM_PRESETS
    model: str = ""                     # renderer-specific model id/name

    # MVSEP cloud
    mvsep_token: str = ""
    mvsep_sep_type: str = ""            # render_id from /api/app/algorithms
    mvsep_poll_seconds: int = 15

    # Studio PC agent
    pc_url: str = ""                    # e.g. http://studio-pc.local:8765
    pc_token: str = ""

    # Ableton
    observatory_root: str = ""
    live_app: str = ""
    live_template: str = ""
    warp_stems: bool = True
    warp_mode: str = "complex"          # beats | tones | texture | repitch | complex | complex_pro
    open_after_build: bool = True

    # Auditioning
    preview_bytes: int = 2 * 1024 * 1024  # roughly 40-60 s of MP3, enough to judge a loop
    player: str = "afplay"

    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:

        base = default_config_dir()

        if not self.work_dir:
            self.work_dir = str(base / "digging")

        if not self.output_dir:
            self.output_dir = str(Path(self.work_dir) / "sessions")

        if not self.observatory_root:
            self.observatory_root = str(default_observatory_root())

        if not self.live_app:
            self.live_app = str(default_live_app())

    @property
    def path(self) -> Path:
        return default_config_dir() / "digging.json"

    @property
    def stems(self) -> tuple[str, ...]:
        return STEM_PRESETS.get(self.preset, STEM_PRESETS["4"])

    @property
    def work_path(self) -> Path:
        return Path(self.work_dir).expanduser()

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir).expanduser()

    def ensure_dirs(self) -> None:
        for folder in (
            self.work_path, self.output_path,
            self.work_path / "downloads", self.work_path / "stems",
        ):
            folder.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls, path: Path | None = None) -> "DiggingSettings":
        """Load settings, falling back to defaults for missing or corrupt files."""

        target = path or (default_config_dir() / "digging.json")

        try:
            with target.open(encoding="utf-8") as handle:
                raw = json.load(handle)

        except (OSError, ValueError):
            return cls()

        known = {key for key in cls.__dataclass_fields__ if key != "extra"}
        settings = cls(**{key: value for key, value in raw.items() if key in known})
        settings.extra = {key: value for key, value in raw.items() if key not in known}
        return settings

    def save(self, path: Path | None = None) -> Path:
        target = path or self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload.update(payload.pop("extra", None) or {})

        tmp = target.with_suffix(".json.tmp")

        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)

        tmp.replace(target)
        return target
