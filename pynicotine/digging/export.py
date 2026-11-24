# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Export the auditioned audio to a real file.

The Dig player drag-and-drops audio into a DAW, so whatever is loaded (a
catalogue preview, a full YouTube match, or a downloaded peer file) gets written
as a 16-bit WAV that any application can accept.
"""

from __future__ import annotations

import re
import wave

from pathlib import Path


def safe_name(value: str, fallback: str = "digging", limit: int = 80) -> str:
    import unicodedata

    folded = unicodedata.normalize("NFKD", value)
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    cleaned = re.sub(r"[^A-Za-z0-9&+_. -]+", "", folded).strip(" .-_")
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return (cleaned or fallback)[:limit]


def write_wav(audio, path: Path, sample_rate: int = 44100) -> Path:
    """Write a float32 (frames, channels) buffer as 16-bit PCM."""

    import numpy as np

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    frames = np.clip(np.asarray(audio, dtype="float32"), -1.0, 1.0)

    if frames.ndim == 1:
        frames = np.stack([frames, frames], axis=1)

    channels = frames.shape[1]
    payload = (frames * 32767.0).astype("<i2").tobytes()

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(payload)

    return path
