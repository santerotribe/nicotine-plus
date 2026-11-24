# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""Studio PC side of the digging pipeline.

Run this on the machine that owns the GPU (the studio PC or a server) and point
Nicotine+ -> digging settings at its address. It accepts an audio file, runs
Demucs and serves the stems back as a zip.

    python -m pynicotine.digging.agent --token SECRET --port 8765

Requires Demucs on the PC: pip install demucs (or pip install -U demucs torch)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

WORK_DIR_DEFAULT = Path.home() / "NicotineStems"
AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".ogg", ".aiff", ".aif", ".m4a", ".opus"}


def _demucs_command() -> list[str] | None:
    executable = shutil.which("demucs")

    if executable:
        return [executable]

    try:
        import importlib.util

        if importlib.util.find_spec("demucs") is not None:
            return [sys.executable, "-m", "demucs"]

    except (ImportError, ValueError):
        pass

    return None


class Job:
    def __init__(self, job_id: str, source: Path, preset: str, model: str) -> None:
        self.id = job_id
        self.source = source
        self.preset = preset
        self.model = model
        self.status = "queued"
        self.progress = 0.0
        self.error = ""
        self.created = time.time()
        self.outdir = source.parent / job_id
        self.result: Path | None = None
        self.lock = threading.Lock()

    def state(self) -> dict:
        with self.lock:
            return {
                "id": self.id,
                "status": self.status,
                "progress": round(self.progress, 4),
                "error": self.error,
                "created": self.created,
            }


class JobRunner:
    def __init__(self, work_dir: Path, model_default: str = "htdemucs") -> None:
        self.work_dir = work_dir
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.model_default = model_default
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def submit(self, name: str, payload: bytes, preset: str, model: str) -> Job:
        job_id = uuid.uuid4().hex[:12]
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name) or "input.wav"
        job_folder = self.work_dir / job_id
        job_folder.mkdir(parents=True, exist_ok=True)
        source = job_folder / safe_name
        source.write_bytes(payload)

        job = Job(job_id, source, preset, model)

        with self.lock:
            self.jobs[job_id] = job

        threading.Thread(target=self._run, args=(job,), daemon=True, name=f"job-{job_id}").start()
        return job

    def _run(self, job: Job) -> None:
        command = _demucs_command()

        if command is None:
            with job.lock:
                job.status = "failed"
                job.error = "demucs is not installed on this machine"

            return

        if job.preset == "2":
            command += ["--two-stems", "vocals"]

        command += ["-n", job.model or self.model_default, "-o", str(job.outdir), str(job.source)]

        with job.lock:
            job.status = "running"

        try:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )

        except OSError as error:
            with job.lock:
                job.status = "failed"
                job.error = str(error)

            return

        assert process.stdout is not None

        for line in process.stdout:
            match = re.search(r"(\d{1,3})%", line)

            if match:
                with job.lock:
                    job.progress = min(0.95, int(match.group(1)) / 100.0)

        return_code = process.wait()

        if return_code != 0:
            with job.lock:
                job.status = "failed"
                job.error = f"demucs exited with {return_code}"

            return

        stems = sorted(
            path for path in job.outdir.rglob("*")
            if path.suffix.lower() in AUDIO_EXTENSIONS
        )

        if not stems:
            with job.lock:
                job.status = "failed"
                job.error = "demucs produced no audio"

            return

        archive = job.outdir / f"{job.id}-stems.zip"

        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as handle:
            for stem in stems:
                handle.write(stem, arcname=stem.name)

        with job.lock:
            job.result = archive
            job.progress = 1.0
            job.status = "done"


class Handler(BaseHTTPRequestHandler):
    runner: JobRunner
    token: str = ""
    server_version = "DiggingAgent/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def _authorized(self) -> bool:
        if not self.token:
            return True

        return self.headers.get("Authorization") == f"Bearer {self.token}"

    def _reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _deny(self) -> None:
        self._reply(HTTPStatus.UNAUTHORIZED, {"error": "bad or missing token"})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]

        if parsed.path == "/health":
            self._reply(HTTPStatus.OK, {
                "status": "ok",
                "demucs": _demucs_command() is not None,
                "jobs": len(self.runner.jobs),
            })
            return

        if not self._authorized():
            self._deny()
            return

        if len(parts) == 2 and parts[0] == "jobs":
            job = self.runner.jobs.get(parts[1])

            if not job:
                self._reply(HTTPStatus.NOT_FOUND, {"error": "unknown job"})
                return

            self._reply(HTTPStatus.OK, job.state())
            return

        if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "result":
            job = self.runner.jobs.get(parts[1])

            if not job or not job.result or not job.result.is_file():
                self._reply(HTTPStatus.CONFLICT, {"error": "job has no result yet"})
                return

            data = job.result.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self._reply(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_PUT(self) -> None:  # noqa: N802
        if not self._authorized():
            self._deny()
            return

        parsed = urlparse(self.path)

        if parsed.path.rstrip("/") != "/jobs":
            self._reply(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        query = parse_qs(parsed.query)
        name = (query.get("name") or ["input.wav"])[0]
        preset = (query.get("preset") or ["4"])[0]
        model = (query.get("model") or [""])[0]
        length = int(self.headers.get("Content-Length") or 0)

        if length <= 0:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": "empty body"})
            return

        payload = self.rfile.read(length)
        job = self.runner.submit(name, payload, preset, model)
        self._reply(HTTPStatus.ACCEPTED, {"id": job.id, "status": job.status})


def serve(port: int = 8765, token: str = "", work_dir: Path | None = None,
          bind: str = "0.0.0.0", model: str = "htdemucs") -> None:

    Handler.runner = JobRunner(work_dir or WORK_DIR_DEFAULT, model_default=model)
    Handler.token = token or os.environ.get("DIGGING_AGENT_TOKEN", "")
    httpd = ThreadingHTTPServer((bind, port), Handler)
    print(f"Digging agent listening on http://{bind}:{port} (work dir: {Handler.runner.work_dir})")

    if not Handler.token:
        print("WARNING: no token configured; anyone on the network can submit jobs")

    if _demucs_command() is None:
        print("WARNING: demucs not found; jobs will fail until it is installed")

    try:
        httpd.serve_forever()

    except KeyboardInterrupt:
        print("Shutting down")

    finally:
        httpd.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stem separation agent for the studio PC")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--token", default="", help="shared secret (or DIGGING_AGENT_TOKEN)")
    parser.add_argument("--work-dir", default=str(WORK_DIR_DEFAULT))
    parser.add_argument("--model", default="htdemucs")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    serve(port=args.port, token=args.token, work_dir=Path(args.work_dir), bind=args.bind, model=args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
