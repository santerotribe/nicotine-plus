# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""MVSEP cloud separation backend (https://mvsep.com/en/full_api).

Flow: create a separation with the audio file, poll its hash until the stems
are ready, then download them.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from pathlib import Path

from pynicotine.digging.renderers.base import (
    ProgressCallback,
    RenderError,
    RenderRequest,
    RenderResult,
    audio_files_in,
    extract_archive,
    organize,
)

MVSEP_API = "https://mvsep.com/api"


class MvsepRenderer:
    name = "mvsep"

    def __init__(self, token: str, sep_type: str, add_opt1: str = "", add_opt2: str = "",
                 poll_seconds: float = 15.0, output_format: str = "1") -> None:

        if not token:
            raise RenderError("MVSEP API token is not configured")

        if not sep_type:
            raise RenderError("MVSEP separation type is not configured")

        self.token = token
        self.sep_type = sep_type
        self.add_opt1 = add_opt1
        self.add_opt2 = add_opt2
        self.poll_seconds = max(2.0, poll_seconds)
        self.output_format = output_format

    # -- HTTP helpers -----------------------------------------------------

    @staticmethod
    def _request(url: str, data: bytes | None = None, headers: dict | None = None,
                 timeout: float = 600.0) -> bytes:

        request = urllib.request.Request(url, data=data, headers=headers or {})

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()

        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", "replace")[:500]
            raise RenderError(f"MVSEP HTTP {error.code}: {body}") from error

        except urllib.error.URLError as error:
            raise RenderError(f"MVSEP unreachable: {error.reason}") from error

    def _create(self, request: RenderRequest) -> str:
        """Upload the source file and return the separation hash."""

        boundary = "----schema-digging-boundary"
        parts: list[bytes] = []

        def add_field(name: str, value: str) -> None:
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
            )

        add_field("api_token", self.token)
        add_field("sep_type", self.sep_type)
        add_field("add_opt1", self.add_opt1)
        add_field("add_opt2", self.add_opt2)
        add_field("output_format", self.output_format)
        add_field("is_demo", "0")

        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"audiofile\"; "
            f"filename=\"{request.source.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
        )
        parts.append(request.source.read_bytes())
        parts.append(f"\r\n--{boundary}--\r\n".encode())

        payload = b"".join(parts)
        raw = self._request(
            f"{MVSEP_API}/separation/create",
            data=payload,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            timeout=1800.0,
        )

        try:
            parsed = json.loads(raw)

        except ValueError as error:
            raise RenderError(f"MVSEP returned non-JSON: {raw[:200]!r}") from error

        if not parsed.get("success", True):
            raise RenderError(f"MVSEP rejected the job: {parsed}")

        data = parsed.get("data") or {}
        job_hash = data.get("hash")

        if not job_hash:
            raise RenderError(f"MVSEP did not return a hash: {parsed}")

        return str(job_hash)

    def _poll(self, job_hash: str, timeout: float,
              progress: ProgressCallback | None) -> list[dict]:

        deadline = time.monotonic() + timeout
        url = f"{MVSEP_API}/separation/get?{urllib.parse.urlencode({'hash': job_hash})}"
        waited = 0.0

        while time.monotonic() < deadline:
            raw = self._request(url, timeout=120.0)

            try:
                parsed = json.loads(raw)

            except ValueError:
                parsed = {}

            data = parsed.get("data") or {}
            files = data.get("files") or []

            if files:
                return files

            status = str(data.get("status") or parsed.get("status") or "processing")

            if status.lower() in {"failed", "error"}:
                raise RenderError(f"MVSEP job failed: {data or parsed}")

            if progress:
                progress(f"MVSEP: {status}", min(0.9, 0.1 + (waited / max(1.0, timeout))))

            time.sleep(self.poll_seconds)
            waited += self.poll_seconds

        raise RenderError("timed out waiting for the MVSEP job")

    def _download(self, files: list[dict], outdir: Path,
                  progress: ProgressCallback | None) -> list[Path]:

        outdir.mkdir(parents=True, exist_ok=True)
        downloaded: list[Path] = []

        for index, entry in enumerate(files):
            url = str(entry.get("url") or "").replace("\\/", "/")
            name = str(entry.get("download") or f"stem-{index}.wav")

            if not url:
                continue

            target = outdir / Path(name).name

            if progress:
                progress(f"downloading {target.name}", 0.9 + (0.1 * index / max(1, len(files))))

            target.write_bytes(self._request(url, timeout=1800.0))
            downloaded.append(target)

        if not downloaded:
            raise RenderError("MVSEP finished but no files were available")

        return downloaded

    # -- public API -------------------------------------------------------

    def separate(self, request: RenderRequest, progress: ProgressCallback | None = None) -> RenderResult:

        if progress:
            progress("uploading to MVSEP", 0.05)

        job_hash = self._create(request)

        if progress:
            progress(f"queued as {job_hash}", 0.1)

        entries = self._poll(job_hash, request.timeout, progress)
        outdir = request.outdir
        files = self._download(entries, outdir, progress)

        # Providers sometimes ship one archive instead of loose stems
        archives = [path for path in files if path.suffix.lower() == ".zip"]

        if archives:
            for archive in archives:
                files.extend(extract_archive(archive, outdir))
                files.remove(archive)

        stems = organize(audio_files_in(outdir), request.preset)

        if not stems:
            raise RenderError("MVSEP returned no recognisable stems")

        return RenderResult(stems=stems, renderer=self.name, job_id=job_hash, files=files)


def list_algorithms() -> list[dict]:
    """Return the catalogue of MVSEP algorithms (no token required)."""

    raw = MvsepRenderer._request(f"{MVSEP_API}/app/algorithms", timeout=60.0)

    try:
        parsed = json.loads(raw)

    except ValueError as error:
        raise RenderError("MVSEP algorithms endpoint returned non-JSON") from error

    if isinstance(parsed, dict):
        parsed = parsed.get("data") or parsed.get("algorithms") or []

    return [entry for entry in parsed if isinstance(entry, dict)]
