"""Refuse obvious credentials in files Git would commit. A fast local guard; gitleaks runs in CI as well.

Scans tracked files and untracked files that are not ignored. Exit 1 and print file:line for each hit.
A line can opt out with the marker ``secret-scan: allow`` when it holds a documented, non-secret example.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "API key (sk-)": re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,}\b"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "assigned secret": re.compile(
        r"(?i)\b(?:password|passwd|secret|api_key|apikey|token)\s*[:=]\s*['\"][^'\"\s]{16,}['\"]"
    ),
}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".sqlite", ".lock", ".woff", ".woff2"}


def files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ROOT / line for line in out.splitlines() if line]


def main() -> int:
    hits = []
    for path in files():
        if path.suffix in SKIP_SUFFIXES or not path.is_file() or path.stat().st_size > 5_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if "secret-scan: allow" in line:
                continue
            for name, pattern in PATTERNS.items():
                if pattern.search(line):
                    hits.append(f"{path.relative_to(ROOT)}:{n}: possible {name}")
    for h in hits:
        print(h, file=sys.stderr)
    print(f"secret scan: {len(hits)} finding(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
