"""Serve a simulation host: ``uv run --project runtimes/sim-host python -m pap_sim_host.server --catalog <file>``.

Binds to 127.0.0.1 by default (set --host deliberately to expose it; there is no authentication here: the operator
decides who can reach it, as for the other instrument endpoints). Thing Descriptions: ``/thing_descriptions/``.
Artifact bytes: ``GET /simulation-host/runs/<run_id>/artifacts/<name>`` (listed artifacts of recorded runs only).
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import labthings_fastapi as lt
import uvicorn
from fastapi import HTTPException
from fastapi.responses import FileResponse

from .catalog import load_catalog
from .runner import Host, HostError
from .things import SimulationHost, configure

THING = "simulation-host"


def create_server(catalog_path: Path, work_dir: Path | None = None) -> lt.ThingServer:
    catalog = load_catalog(catalog_path)
    work = work_dir or Path(os.environ.get("PAP_SIMHOST_WORK") or tempfile.mkdtemp(prefix="pap-simhost-"))
    host = Host(catalog, catalog_path.resolve().parent, work)
    configure(host)
    folder = os.environ.get("PAP_SIMHOST_SETTINGS") or tempfile.mkdtemp(prefix="pap-simhost-settings-")
    server = lt.ThingServer.from_things({THING: SimulationHost}, settings_folder=folder)

    @server.app.get(f"/{THING}/runs/{{run_id}}/artifacts/{{name}}", include_in_schema=False)
    def artifact(run_id: str, name: str) -> FileResponse:
        try:
            path, a = host.artifact(run_id, name)
        except HostError as e:
            raise HTTPException(status_code=404 if e.code == "not_found" else 409, detail=e.message) from None
        return FileResponse(path, media_type=a["media_type"], headers={"X-Artifact-SHA256": a["sha256"]})

    return server


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--catalog", default=os.environ.get("PAP_SIMHOST_CATALOG"), required=not os.environ.get("PAP_SIMHOST_CATALOG")
    )
    ap.add_argument("--host", default=os.environ.get("PAP_SIMHOST_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PAP_SIMHOST_PORT", "8300")))
    ap.add_argument(
        "--work", default=None, help="where runs and their artifacts are kept (default: a temporary folder)"
    )
    a = ap.parse_args()
    server = create_server(Path(a.catalog), Path(a.work) if a.work else None)
    uvicorn.run(server.app, host=a.host, port=a.port, ws="websockets-sansio", log_level="warning")


if __name__ == "__main__":
    main()
