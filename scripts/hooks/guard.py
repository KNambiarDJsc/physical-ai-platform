"""Claude Code PreToolUse guard for this repository.

Reads the hook payload (JSON on stdin). Exit 2 blocks the tool call and shows stderr to the agent; exit 0 allows.
Blocks:
  * Edit/Write outside this repository, or inside the pinned engine source (.engine/), or of engine.lock.json's
    commit without a decision (edits to the lock are allowed; the bridge tests catch a wrong pin);
  * Bash `git push` (pushing needs the user), and `git commit` when the secret scan finds something.
Deterministic, no network, finishes in well under a second (the secret scan only runs on commit).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTECTED = [ROOT / ".engine"]


def block(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(2)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return  # not a hook payload; do nothing
    tool = payload.get("tool_name", "")
    data = payload.get("tool_input", {}) or {}

    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        raw = data.get("file_path") or data.get("notebook_path") or ""
        if not raw:
            return
        path = Path(raw).resolve()
        if ROOT not in path.parents and path != ROOT:
            block(
                f"guard: {path} is outside this repository. Sibling repositories (OpenMHS, AI Studio) are read-only "
                "from here; record interface needs in docs/engine-contract-gaps.md."
            )
        for p in PROTECTED:
            if p == path or p in path.parents:
                block(f"guard: {path} is the pinned engine build area; rebuild with scripts/build-openmhs.sh instead.")

    if tool == "Bash":
        cmd = data.get("command", "")
        if re.search(r"\bgit\s+push\b", cmd):
            block("guard: pushing needs explicit approval from the user; leave the commit local.")
        if re.search(r"--dangerously-skip-permissions|--allow-dangerously-skip-permissions", cmd):
            block("guard: permission bypass is not allowed in this repository.")
        if re.search(r"\bgit\s+commit\b", cmd):
            r = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "check_secrets.py")], capture_output=True, text=True
            )
            if r.returncode != 0:
                block("guard: secret scan failed, commit refused:\n" + r.stderr[-2000:])


if __name__ == "__main__":
    main()
