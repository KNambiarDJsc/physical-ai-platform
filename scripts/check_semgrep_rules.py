"""Check that every project Semgrep rule fires where it should and nowhere else.

    uvx --from semgrep==1.183.0 python scripts/check_semgrep_rules.py   (or: semgrep on PATH)

The samples in .semgrep/rules.{py,tsx} carry `ruleid: <id>` comments on the line before code a rule must flag,
and `ok: <id>` before code it must not flag. (`semgrep --test` does the same, but crashes on Windows paths.)
Exit 0 only if findings equal the `ruleid` annotations exactly and every rule has at least one.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / ".semgrep" / "rules.yml"
SAMPLES = [ROOT / ".semgrep" / "rules.py", ROOT / ".semgrep" / "rules.tsx"]
ANNOT = re.compile(r"(?:#|//)\s*(ruleid|ok):\s*([\w-]+)")


def main() -> int:
    semgrep = shutil.which("semgrep")
    if semgrep is None:
        print("semgrep not found on PATH", file=sys.stderr)
        return 2
    expected: set[tuple[str, int, str]] = set()
    ok: set[tuple[str, int, str]] = set()
    for f in SAMPLES:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), start=1):
            m = ANNOT.search(line)
            if m:
                (expected if m.group(1) == "ruleid" else ok).add((f.name, i + 1, m.group(2)))
    argv = [semgrep, "scan", "--config", str(RULES), "--json", "--metrics=off", "--disable-version-check"]
    argv += ["--x-ignore-semgrepignore-files", *map(str, SAMPLES)]
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        cwd=ROOT,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(proc.stdout[-2000:], proc.stderr[-2000:], file=sys.stderr)
        return 2
    found = {(Path(r["path"]).name, r["start"]["line"], r["check_id"].rsplit(".", 1)[-1]) for r in out["results"]}
    rule_ids = set(re.findall(r"^\s*- id:\s*([\w-]+)", RULES.read_text(encoding="utf-8"), re.M))
    missing = expected - found
    unexpected = found - expected
    untested = rule_ids - {r for _, _, r in expected}
    for label, items in (("missed", missing), ("unexpected", unexpected), ("false positive on ok:", found & ok)):
        for item in sorted(items):
            print(f"{label}: {item}")
    for r in sorted(untested):
        print(f"rule without a ruleid sample: {r}")
    if missing or unexpected or untested:
        return 1
    print(f"{len(rule_ids)} rules, {len(expected)} expected findings, {len(ok)} ok cases: all as annotated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
