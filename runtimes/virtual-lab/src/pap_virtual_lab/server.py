"""Serve the virtual laboratory: ``uv run --project runtimes/virtual-lab python -m pap_virtual_lab.server``.

Binds to 127.0.0.1 by default. Thing Descriptions: ``/thing_descriptions/`` (all) and ``/<thing>/`` (one).
"""

from __future__ import annotations

import argparse
import os
import tempfile

import labthings_fastapi as lt
import uvicorn

from .things import Balance, SimulationControl, SyringePump

THINGS = {"pump": SyringePump, "balance": Balance, "simulation": SimulationControl}


def create_server() -> lt.ThingServer:
    # LabThings keeps per-Thing settings in a folder; a temporary one keeps the image's filesystem read-only.
    folder = os.environ.get("PAP_VLAB_SETTINGS") or tempfile.mkdtemp(prefix="pap-vlab-")
    return lt.ThingServer.from_things(THINGS, settings_folder=folder)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default=os.environ.get("PAP_VLAB_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PAP_VLAB_PORT", "8100")))
    a = ap.parse_args()
    uvicorn.run(create_server().app, host=a.host, port=a.port, ws="websockets-sansio", log_level="warning")


if __name__ == "__main__":
    main()
