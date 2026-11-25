# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Studio PC separation backend.

Talks to the small agent in pynicotine/digging/agent.py, which runs Demucs on
the studio machine:

    PUT  /jobs?name=<file>&preset=<n>&model=<name>   body: audio bytes
    GET  /jobs/<id>                                   status + progress
    GET  /jobs/<id>/result                            zip of stems
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from pynicotine.digging.renderers.base import (
    ProgressCallback,
    RenderError,
    RenderRequest,
    RenderResult,
    audio_files_in,
    extract_archive,
    organize,
)


class PcAgentRenderer:
    name = "pc"

    def __init__(self, base_url: str, token: str = "", poll_seconds: float = 3.0) -> None:

        if not base_url:
            raise RenderError("studio PC agent URL is not configured")

        self.base_url = base_url.rstrip("/")
        self.token = token
        self.poll_seconds = max(1.0, poll_seconds)

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

        if extra:
            headers.update(extra)

        return headers

    def _request(self, url: str, data: bytes | None = None, method: str | None = None,
                 timeout: float = 600.0) -> bytes:

        request = urllib.request.Request(url, data=data, headers=self._headers(), method=method)

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()

        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", "replace")[:400]
            raise RenderError(f"agent HTTP {error.code}: {body}") from error

        except urllib.error.URLError as error:
            raise RenderError(f"studio PC unreachable: {error.reason}") from error

    def health(self) -> dict:
        raw = self._request(f"{self.base_url}/health", timeout=15.0)

        try:
            return json.loads(raw)

        except ValueError:
            return {"status": "unknown"}

    def separate(self, request: RenderRequest, progress: ProgressCallback | None = None) -> RenderResult:

        query = urllib.parse.urlencode({
            "name": request.source.name,
            "preset": request.preset,
            "model": request.model,
        })

        if progress:
            progress("uploading to studio PC", 0.05)

        raw = self._request(f"{self.base_url}/jobs?{query}", data=request.source.read_bytes(),
                            method="PUT", timeout=3600.0)

        try:
            job = json.loads(raw)

        except ValueError as error:
            raise RenderError("agent returned a non-JSON job response") from error

        job_id = str(job.get("id") or "")

        if not job_id:
            raise RenderError(f"agent did not return a job id: {job}")

        deadline = time.monotonic() + request.timeout

        while time.monotonic() < deadline:
            state = json.loads(self._request(f"{self.base_url}/jobs/{job_id}", timeout=30.0))
            status = str(state.get("status") or "")
            fraction = float(state.get("progress") or 0.0)

            if progress:
                progress(f"studio PC: {status}", min(0.9, 0.1 + (0.8 * fraction)))

            if status == "done":
                break

            if status == "failed":
                raise RenderError(f"studio PC failed: {state.get('error')}")

            time.sleep(self.poll_seconds)

        else:
            raise RenderError("timed out waiting for the studio PC")

        archive = request.outdir / f"{job_id}.zip"
        request.outdir.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(self._request(f"{self.base_url}/jobs/{job_id}/result", timeout=1800.0))
        files = extract_archive(archive, request.outdir / "stems")
        archive.unlink(missing_ok=True)
        stems = organize(audio_files_in(request.outdir / "stems"), request.preset)

        if not stems:
            raise RenderError("studio PC returned no recognisable stems")

        return RenderResult(stems=stems, renderer=self.name, job_id=job_id, files=files)
