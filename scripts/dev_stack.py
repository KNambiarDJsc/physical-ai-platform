"""Run the whole platform locally without Docker: PostgreSQL (pgserver), migrations, API, worker, web.

    uv run python scripts/dev_stack.py            # until Ctrl-C
    uv run python scripts/dev_stack.py --ready-file var/stack.json   # write URLs when everything answers

The worker is supervised: if it exits (or is killed, as the e2e recovery test does) it is started again, like a
container restart policy, and its PID is written to var/dev-stack/worker.pid. Development only (PAP_AUTH_MODE=dev).
Everything lives under var/ (gitignored). The web app must be built first (npm --prefix apps/web run build).
Docker Compose (INF-003) replaces this once Docker is available.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "services" / "api"


def wait(url: str, seconds: float = 90) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:  # noqa: S310 (local URL)
                if r.status < 500:
                    return
        except OSError:
            pass
        time.sleep(0.5)
    raise TimeoutError(url)


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


# On POSIX each component runs in its own process group and the whole group is stopped: npm does not pass SIGTERM
# on to `next start`, which was left running and then answered the next stack's readiness check (found on CI).
GROUP: dict[str, Any] = {} if sys.platform == "win32" else {"start_new_session": True}


def stop_process(p: subprocess.Popen[bytes]) -> None:
    if p.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, check=False)
        return
    for sig, grace in ((signal.SIGTERM, 10.0), (signal.SIGKILL, 5.0)):
        try:
            os.killpg(p.pid, sig)
        except ProcessLookupError:
            return
        try:
            p.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            continue


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-port", type=int, default=8000)
    ap.add_argument("--web-port", type=int, default=3000)
    ap.add_argument("--ready-file")
    ap.add_argument("--state-dir", default=str(ROOT / "var"), help="database, artifacts and work files go here")
    ap.add_argument("--stop-file", help="stop cleanly (database included) when this file appears")
    ns = ap.parse_args()
    VAR = Path(ns.state_dir).resolve()
    stop = Path(ns.stop_file) if ns.stop_file else None
    if stop:
        stop.unlink(missing_ok=True)
    busy = [port for port in (ns.api_port, ns.web_port) if not port_free(port)]
    if busy:  # a leftover server would answer the readiness checks below in place of ours
        print(f"port(s) {busy} already in use; stop whatever holds them first", file=sys.stderr)
        return 2

    import pgserver
    import psycopg
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.engine import make_url

    (VAR / "dev-pg").mkdir(parents=True, exist_ok=True)
    pg = pgserver.get_server(str(VAR / "dev-pg"), cleanup_mode="stop")
    admin = pg.get_uri()
    with psycopg.connect(admin, autocommit=True) as c:
        if not c.execute("select 1 from pg_database where datname = 'pap_dev'").fetchone():
            c.execute("CREATE DATABASE pap_dev")
    # Parsed, not string-edited: on Linux pgserver uses a Unix socket and the URI carries its directory in the query
    # (?host=/path/...), which splitting on "/" cut apart (found on CI).
    db = make_url(admin).set(drivername="postgresql+psycopg", database="pap_dev").render_as_string(hide_password=False)
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.attributes["url"] = db
    command.upgrade(cfg, "head")

    env = {
        **os.environ,
        "PAP_ENV": "development",
        "PAP_AUTH_MODE": os.environ.get("PAP_AUTH_MODE", "dev"),  # oidc for the sign-in tests (smoke.sh --oidc)
        "PAP_DATABASE_URL": db,
        "PAP_STORAGE_PATH": str(VAR / "artifacts"),
        "PAP_WORK_PATH": str(VAR / "work"),
        "PAP_WORKER_LEASE_S": "10",
        "PYTHONPATH": str(API_DIR),
    }
    run_dir = VAR / "dev-stack"
    run_dir.mkdir(parents=True, exist_ok=True)
    pid_file = run_dir / "worker.pid"

    def start_worker() -> subprocess.Popen[bytes]:
        w = subprocess.Popen([sys.executable, "-m", "app.workers.run", "--poll", "0.5"], cwd=API_DIR, env=env, **GROUP)
        pid_file.write_text(str(w.pid), encoding="utf-8")
        return w

    api_cmd = [sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port"]
    procs = [
        subprocess.Popen([*api_cmd, str(ns.api_port)], cwd=API_DIR, env=env, **GROUP),
        start_worker(),
        subprocess.Popen(
            ["npm", "--prefix", str(ROOT / "apps" / "web"), "run", "start", "--", "-p", str(ns.web_port)],
            env={**env, "PAP_API_URL": f"http://127.0.0.1:{ns.api_port}", "NEXT_TELEMETRY_DISABLED": "1"},
            shell=sys.platform == "win32",  # npm is a .cmd on Windows; the command is fixed, no user input
            **GROUP,
        ),
    ]
    try:
        wait(f"http://127.0.0.1:{ns.api_port}/healthz")
        wait(f"http://127.0.0.1:{ns.web_port}/")
        if any(p.poll() is not None for p in procs):
            print("a component exited during start-up; stopping", file=sys.stderr)
            return 1
        info = {
            "api": f"http://127.0.0.1:{ns.api_port}",
            "web": f"http://127.0.0.1:{ns.web_port}",
            "database": db,
            "worker_pid_file": str(pid_file),
        }
        print(json.dumps(info), flush=True)
        if ns.ready_file:
            Path(ns.ready_file).write_text(json.dumps(info), encoding="utf-8")
        while procs[0].poll() is None and procs[2].poll() is None:
            if stop and stop.exists():
                print("stop file found; stopping", file=sys.stderr, flush=True)
                return 0
            if procs[1].poll() is not None:
                print(f"worker exited ({procs[1].returncode}); starting a new one", file=sys.stderr, flush=True)
                procs[1] = start_worker()
            time.sleep(0.5)
        print("a component exited; stopping", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for p in procs:
            stop_process(p)
        pg.cleanup()


if __name__ == "__main__":
    sys.exit(main())
