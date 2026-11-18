"""Check harness/features.json: structure, ids, dependencies, statuses, and evidence for verified features.

Exit 0 when the registry is consistent, 1 otherwise. Prints the next eligible features (unfinished, all
dependencies verified) so a session or scripts/loop.sh can pick one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = (
    "id",
    "title",
    "priority",
    "depends_on",
    "description",
    "acceptance",
    "tests",
    "paths",
    "status",
    "verification",
    "limitations",
)


def check(registry: dict) -> list[str]:
    errors: list[str] = []
    allowed = set(registry.get("statuses", []))
    features = registry.get("features", [])
    ids = [f.get("id") for f in features]
    seen: set[str] = set()
    for fid in ids:
        if fid in seen:
            errors.append(f"duplicate id {fid}")
        seen.add(fid)
    by_id = {f["id"]: f for f in features if "id" in f}
    for f in features:
        fid = f.get("id", "<no id>")
        for key in REQUIRED:
            if key not in f:
                errors.append(f"{fid}: missing {key}")
        if f.get("status") not in allowed:
            errors.append(f"{fid}: status {f.get('status')!r} not in {sorted(allowed)}")
        if not f.get("acceptance"):
            errors.append(f"{fid}: no acceptance criteria")
        for dep in f.get("depends_on", []):
            if dep not in by_id:
                errors.append(f"{fid}: depends on unknown {dep}")
        if f.get("status") == "verified":
            ev = f.get("verification", {})
            if not ev.get("evidence") or not ev.get("verified_at"):
                errors.append(f"{fid}: verified without evidence and verified_at")
            for dep in f.get("depends_on", []):
                if by_id.get(dep, {}).get("status") != "verified":
                    errors.append(f"{fid}: verified while dependency {dep} is not")
        if f.get("status") == "blocked" and not f.get("limitations"):
            errors.append(f"{fid}: blocked without a recorded reason in limitations")
    # cycle check
    state: dict[str, int] = {}

    def visit(n: str, path: list[str]) -> None:
        if state.get(n) == 1:
            errors.append("dependency cycle: " + " -> ".join([*path, n]))
            return
        if state.get(n) == 2 or n not in by_id:
            return
        state[n] = 1
        for d in by_id[n].get("depends_on", []):
            visit(d, [*path, n])
        state[n] = 2

    for n in by_id:
        visit(n, [])
    return errors


def eligible(registry: dict) -> list[dict]:
    by_id = {f["id"]: f for f in registry["features"]}
    out = [
        f
        for f in registry["features"]
        if f["status"] in ("unstarted", "in_progress")
        and all(by_id[d]["status"] == "verified" for d in f["depends_on"])
    ]
    return sorted(out, key=lambda f: (f["priority"], f["status"] != "in_progress", f["id"]))


def main() -> int:
    registry = json.loads((ROOT / "harness" / "features.json").read_text(encoding="utf-8"))
    errors = check(registry)
    for e in errors:
        print(f"features.json: {e}", file=sys.stderr)
    counts: dict[str, int] = {}
    for f in registry["features"]:
        counts[f["status"]] = counts.get(f["status"], 0) + 1
    print("features: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    nxt = eligible(registry)
    print("eligible next: " + (", ".join(f"{f['id']}({f['status']})" for f in nxt[:6]) or "none"))
    if "--next" in sys.argv and nxt:
        print(nxt[0]["id"])
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
