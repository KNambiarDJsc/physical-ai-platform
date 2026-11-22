"""Start the real virtual laboratory (runtimes/virtual-lab) for tests and local runs. No mocks."""

from __future__ import annotations

import contextlib
import os
import shutil
import socket
import subprocess
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import httpx


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextlib.contextmanager
def _serve(cmd: list[str], env: dict[str, str], port: int, what: str) -> Iterator[str]:
    """Start a LabThings server, wait until it answers, yield its URL, stop it afterwards.

    The server's stderr goes to a temporary file, never to an unread pipe: a pipe nobody drains fills after a few
    logged tracebacks and then blocks the server's logging call inside an action thread, so the invocation never
    leaves ``running`` (seen with the simulation host after about seven refused calls).
    """
    with tempfile.TemporaryFile() as err_file:
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=err_file)
        url = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 120
            while True:
                if proc.poll() is not None:
                    err_file.seek(0)
                    err = err_file.read().decode(errors="replace")
                    raise RuntimeError(f"{what} exited during start-up: {err[-2000:]}")
                with contextlib.suppress(httpx.HTTPError):
                    if httpx.get(f"{url}/thing_descriptions/", timeout=2).status_code == 200:
                        break
                if time.monotonic() > deadline:
                    raise RuntimeError(f"{what} did not answer within 120 s")
                time.sleep(0.3)
            yield url
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=15)


def _uv() -> str:
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv is required to start the virtual laboratory or the simulation host")
    return uv


@contextlib.contextmanager
def run_virtual_lab(repo_root: Path, port: int | None = None, seed: int = 7) -> Iterator[str]:
    """Yield the base URL of a freshly started virtual lab; stop it afterwards."""
    port = port or free_port()
    cmd = [
        _uv(), "run", "--quiet", "--project", str(repo_root / "runtimes" / "virtual-lab"), "python", "-m",
        "pap_virtual_lab.server", "--port", str(port),
    ]  # fmt: skip
    with _serve(cmd, {**os.environ, "PAP_VLAB_SEED": str(seed)}, port, "virtual lab") as url:
        yield url


@contextlib.contextmanager
def run_sim_host(repo_root: Path, catalog: Path, work: Path | None = None, port: int | None = None) -> Iterator[str]:
    """Yield the base URL of a freshly started simulation host (runtimes/sim-host) for a catalog; stop it afterwards."""
    port = port or free_port()
    cmd = [
        _uv(), "run", "--quiet", "--project", str(repo_root / "runtimes" / "sim-host"), "python", "-m",
        "pap_sim_host.server", "--catalog", str(catalog), "--port", str(port),
    ]  # fmt: skip
    if work is not None:
        cmd += ["--work", str(work)]
    with _serve(cmd, dict(os.environ), port, "simulation host") as url:
        yield url
