"""Claude Code Stop hook: do not end a session that changed code without a hand-off note.

If source files changed (uncommitted or in commits since the last progress.md change) but harness/progress.md
did not, ask the agent once to update it. ``stop_hook_active`` is set when the agent is already continuing
because of this hook, so it never blocks twice in a row (no infinite loop).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CODE = ("services/", "packages/", "apps/", "scripts/", "integrations/", "infrastructure/")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    if payload.get("stop_hook_active"):
        return
    changed = {line[3:].strip() for line in git("status", "--porcelain").splitlines()}
    last = git("log", "-1", "--format=%H", "--", "harness/progress.md").strip()
    if last:
        changed |= set(git("diff", "--name-only", f"{last}..HEAD").splitlines())
    code = [c for c in changed if c.startswith(CODE)]
    if code and "harness/progress.md" not in changed:
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": "Code changed but harness/progress.md has no hand-off entry. Add what changed, the "
                    "test evidence, the next step and anything uncommitted, then stop.",
                }
            )
        )


if __name__ == "__main__":
    main()
    sys.exit(0)
