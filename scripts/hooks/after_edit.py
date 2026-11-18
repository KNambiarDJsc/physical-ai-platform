"""Claude Code PostToolUse hook: format and lint the one Python file that was just edited.

Targeted on purpose (no test runs here; tests belong to the engineering loop). Lint findings that remain after
auto-fix are reported back to the agent (exit 2) so they are fixed while the context is fresh.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    raw = (payload.get("tool_input") or {}).get("file_path", "")
    if not raw.endswith(".py"):
        return
    path = Path(raw).resolve()
    if ROOT not in path.parents or ".engine" in path.parts or not path.exists():
        return
    env = {**os.environ, "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", "D:/uv-cache")}
    subprocess.run(["uv", "run", "--quiet", "ruff", "format", str(path)], cwd=ROOT, env=env, capture_output=True)
    r = subprocess.run(
        ["uv", "run", "--quiet", "ruff", "check", "--fix", str(path)], cwd=ROOT, env=env, capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"ruff found problems in {path.relative_to(ROOT)}:\n{r.stdout[-3000:]}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
