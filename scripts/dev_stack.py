"""Run the whole platform locally without Docker: PostgreSQL (pgserver), migrations, API, worker, web.

    uv run python scripts/dev_stack.py            # until Ctrl-C
    uv run python scripts/dev_stack.py --ready-file var/stack.json   # write URLs when everything answers

Development only (PAP_AUTH_MODE=dev). Everything lives under var/ (gitignored). The web app must be built first
(npm --prefix apps/web run build). Docker Compose (INF-003) replaces this once Docker is available.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "services" / "api"
VAR = ROOT / "var"


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-port", type=int, default=8000)
    ap.add_argument("--web-port", type=int, default=3000)
    ap.add_argument("--ready-file")
    ns = ap.parse_args()

    import pgserver
    import psycopg
    from alembic import command
    from alembic.config import Config

    (VAR / "dev-pg").mkdir(parents=True, exist_ok=True)
    pg = pgserver.get_server(str(VAR / "dev-pg"), cleanup_mode="stop")
    admin = pg.get_uri()
    with psycopg.connect(admin, autocommit=True) as c:
        if not c.execute("select 1 from pg_database where datname = 'pap_dev'").fetchone():
            c.execute("CREATE DATABASE pap_dev")
    db = admin.replace("postgresql://", "postgresql+psycopg://", 1).rsplit("/", 1)[0] + "/pap_dev"
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.attributes["url"] = db
    command.upgrade(cfg, "head")

    env = {
        **os.environ,
        "PAP_ENV": "development",
        "PAP_AUTH_MODE": "dev",
        "PAP_DATABASE_URL": db,
        "PAP_STORAGE_PATH": str(VAR / "artifacts"),
        "PAP_WORK_PATH": str(VAR / "work"),
        "PAP_WORKER_LEASE_S": "10",
        "PYTHONPATH": str(API_DIR),
    }
    api_cmd = [sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port"]
    procs = [
        subprocess.Popen([*api_cmd, str(ns.api_port)], cwd=API_DIR, env=env),
        subprocess.Popen([sys.executable, "-m", "app.workers.run", "--poll", "0.5"], cwd=API_DIR, env=env),
        subprocess.Popen(
            ["npm", "--prefix", str(ROOT / "apps" / "web"), "run", "start", "--", "-p", str(ns.web_port)],
            env={**env, "PAP_API_URL": f"http://127.0.0.1:{ns.api_port}", "NEXT_TELEMETRY_DISABLED": "1"},
            shell=sys.platform == "win32",  # npm is a .cmd on Windows; the command is fixed, no user input
        ),
    ]
    try:
        wait(f"http://127.0.0.1:{ns.api_port}/healthz")
        wait(f"http://127.0.0.1:{ns.web_port}/")
        info = {"api": f"http://127.0.0.1:{ns.api_port}", "web": f"http://127.0.0.1:{ns.web_port}", "database": db}
        print(json.dumps(info), flush=True)
        if ns.ready_file:
            Path(ns.ready_file).write_text(json.dumps(info), encoding="utf-8")
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        print("a component exited; stopping", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for p in procs:
            if p.poll() is None:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
                else:
                    p.send_signal(signal.SIGTERM)
        pg.cleanup()


if __name__ == "__main__":
    sys.exit(main())
