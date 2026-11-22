"""Self-test scenarios for the simulation host. This is NOT a simulator: a small, honest computation that exercises
the host's plumbing (parameters in, measurements and artifacts out, failures, time) without needing any simulator.

    python scenario.py <mode> <run_dir> <params.json>
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def main() -> int:
    mode, run_dir, params_file = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    p = json.loads(params_file.read_text(encoding="utf-8"))
    if mode == "sum":
        rows = int(p.get("rows", 10))
        with (run_dir / "telemetry.csv").open("w", encoding="utf-8", newline="\n") as f:
            f.write("i,value\n")
            for i in range(rows):
                f.write(f"{i},{p['a'] + i * p['b']}\n")
        result = {
            "measurements": {"sum": p["a"] + p["b"], "rows": rows},
            "artifacts": {"telemetry": "telemetry.csv"},
            "identity": {"kind": "selftest", "note": "a deterministic computation, not a simulation"},
        }
    elif mode == "sleep":
        t0 = time.monotonic()
        time.sleep(float(p["seconds"]))
        result = {"measurements": {"slept_s": round(time.monotonic() - t0, 3)}, "artifacts": {}}
    elif mode == "drive":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from drive import run as drive

        result = drive(p, run_dir)
    elif mode == "fail":
        print("the self-test scenario was asked to fail", file=sys.stderr)
        return 3
    elif mode == "no-measurement":
        result = {"measurements": {}, "artifacts": {}}
    elif mode == "escape":
        result = {"measurements": {"sum": 1}, "artifacts": {"telemetry": "../../../outside.csv"}}
    else:
        print(f"unknown mode {mode}", file=sys.stderr)
        return 2
    (run_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
