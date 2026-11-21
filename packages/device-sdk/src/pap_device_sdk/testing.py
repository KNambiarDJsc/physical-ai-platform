"""Start the real virtual laboratory (runtimes/virtual-lab) for tests and local runs. No mocks."""

from __future__ import annotations

import contextlib
import os
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import httpx


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextlib.contextmanager
def run_virtual_lab(repo_root: Path, port: int | None = None, seed: int = 7) -> Iterator[str]:
    """Yield the base URL of a freshly started virtual lab; stop it afterwards."""
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv is required to start the virtual laboratory")
    port = port or free_port()
    env = {**os.environ, "PAP_VLAB_SEED": str(seed)}
    proc = subprocess.Popen(
        [
            uv,
            "run",
            "--quiet",
            "--project",
            str(repo_root / "runtimes" / "virtual-lab"),
            "python",
            "-m",
            "pap_virtual_lab.server",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            if proc.poll() is not None:
                err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
                raise RuntimeError(f"virtual lab exited during start-up: {err[-2000:]}")
            with contextlib.suppress(httpx.HTTPError):
                if httpx.get(f"{url}/thing_descriptions/", timeout=2).status_code == 200:
                    break
            if time.monotonic() > deadline:
                raise RuntimeError("virtual lab did not answer within 120 s")
            time.sleep(0.3)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
