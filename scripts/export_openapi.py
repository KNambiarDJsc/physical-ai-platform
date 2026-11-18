"""Write (or --check) packages/contracts/openapi.json from the FastAPI application. The TS client is generated from it."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "packages" / "contracts" / "openapi.json"
sys.path.insert(0, str(ROOT / "services" / "api"))


def render() -> str:
    os.environ.setdefault("PAP_AUTH_MODE", "dev")  # configuration only; no server is started
    from app.main import create_app

    return json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("packages/contracts/openapi.json is out of date: run python scripts/export_openapi.py", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
