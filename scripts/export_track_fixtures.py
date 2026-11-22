"""Write the playback tracks of the two committed OpenAMRobot recordings as web unit-test fixtures, and check them.

    uv run python scripts/export_track_fixtures.py           (write)
    uv run python scripts/export_track_fixtures.py --check   (fail if a committed fixture is stale)

The tracks are the API's own output for the real recordings (examples/openamr-cmd-timeout/recorded): the web unit
tests exercise the playback logic on real data, not on numbers made up for the test. They are deterministic, so
``--check`` compares bytes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.twin.track import build_track, canonical  # noqa: E402

RUNS = {"fix": "fix_20261121T185851Z", "main": "main_20261122T053012Z"}
OUT = ROOT / "apps" / "web" / "src" / "lib" / "fixtures"


def fixture(run: str) -> bytes:
    d = ROOT / "examples" / "openamr-cmd-timeout" / "recorded" / run
    mcap = next((d / "bag").glob("*.mcap")).read_bytes()
    summary = json.loads((d / "bag-summary.json").read_text(encoding="utf-8"))
    return canonical(build_track(mcap, summary)) + b"\n"


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for arm, run in RUNS.items():
        path = OUT / f"openamr-{arm}.track.json"
        data = fixture(run)
        if check:
            if not path.is_file() or path.read_bytes() != data:
                stale.append(path.name)
        else:
            OUT.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            print(f"wrote {path.relative_to(ROOT)} ({len(data)} bytes)")
    if stale:
        print(f"stale fixtures: {stale}: run scripts/export_track_fixtures.py")
        return 1
    if check:
        print("track fixtures are up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
