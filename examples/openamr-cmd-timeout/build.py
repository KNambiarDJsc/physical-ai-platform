"""Import and build the command-timeout regression evidence (ROS-004).

    python examples/openamr-cmd-timeout/build.py import --source <runs dir>   (once; needs the original run folders)
    python examples/openamr-cmd-timeout/build.py build [--check]     (reproducible, from this folder)

`import` copies each listed run's result file into recorded/, records its sha256 and the time it was written (the file's
modification time, 1 s resolution: that is all the recordings carry) into runs.json. `build` turns recorded/ into
data/main.csv and data/fix.csv, verifying every sha256 first; with --check it only verifies that the committed CSVs
equal what would be built. Nothing is invented: a value a run did not record stays blank.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs.json"
RECORDED = HERE / "recorded"
DATA = HERE / "data"
COLUMNS = [
    "episode_id",
    "group",
    "procedure",
    "software_state",
    "software_exact",
    "ended_utc",
    "reported_status",
    "driven_before_kill_m",
    "travel_after_kill_m",
    "still_after_kill_s",
    "timeouts_logged",
    "kill_sim_s",
    "evidence_file",
    "evidence_sha256",
    "data_origin",
]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load() -> dict:
    return json.loads(RUNS.read_text(encoding="utf-8"))


def find(sources: list[Path], r: dict) -> Path:
    for s in sources:
        d = s / r.get("source_dir", r["id"])
        if (d / r["file"]).is_file():
            return d
    sys.exit(f"missing original for {r['id']} in {[str(s) for s in sources]}")


def do_import(sources: list[Path], only: str | None = None) -> None:
    """Copy the listed runs' files into recorded/ and record their digests. With ``only``, import that one run and
    keep every other run's recorded evidence exactly as it is."""
    doc = load()
    if only is None:
        doc["evidence"] = {}
    elif only not in {r["id"] for r in doc["runs"]}:
        sys.exit(f"{only} is not listed in runs.json")
    RECORDED.mkdir(exist_ok=True)
    for r in doc["runs"]:
        if only is not None and r["id"] != only:
            continue
        d = find(sources, r)
        src = d / r["file"]
        dst = RECORDED / r["id"] / r["file"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        for extra in r.get("extras", []):  # e.g. the MCAP bag, its summary and the run identity
            e = d / extra
            (shutil.copytree if e.is_dir() else shutil.copyfile)(
                e, RECORDED / r["id"] / extra, **({"dirs_exist_ok": True} if e.is_dir() else {})
            )
        ended = datetime.fromtimestamp(src.stat().st_mtime, UTC).replace(microsecond=0)
        doc["evidence"][r["id"]] = {
            "file": f"recorded/{r['id']}/{r['file']}",
            "sha256": sha256(src),
            "bytes": src.stat().st_size,
            "ended_utc": ended.isoformat().replace("+00:00", "Z"),
            "ended_utc_basis": "modification time of the result file (1 s resolution)",
        }
    RUNS.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"imported {1 if only else len(doc['runs'])} run(s)")


def rows() -> list[dict[str, object]]:
    doc = load()
    out = []
    for r in doc["runs"]:
        ev = doc["evidence"][r["id"]]
        p = HERE / ev["file"]
        if sha256(p) != ev["sha256"]:
            sys.exit(f"{p} does not match its recorded sha256: the recording was changed")
        raw = json.loads(p.read_text(encoding="utf-8"))
        res = raw.get("result", raw)
        out.append(
            {
                "episode_id": r["id"],
                "group": r["arm"],
                "procedure": r["procedure"],
                "software_state": r["software_state"],
                "software_exact": str(r["software_exact"]).lower(),
                "ended_utc": ev["ended_utc"],
                "reported_status": "",  # no controller report exists for these runs
                "driven_before_kill_m": res.get("driven_before_kill_m"),
                "travel_after_kill_m": round(float(res["travel_after_kill_m"]), 4),
                "still_after_kill_s": res.get("still_after_kill_s"),
                "timeouts_logged": res.get("timeouts_logged"),
                "kill_sim_s": res.get("t_kill_sim", res.get("kill_sim_s")),
                "evidence_file": ev["file"],
                "evidence_sha256": ev["sha256"],
                "data_origin": "simulated",
            }
        )
    return out


def render(group: str) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    for r in rows():
        if r["group"] == group:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    return buf.getvalue()


def do_build(check: bool) -> None:
    DATA.mkdir(exist_ok=True)
    for g in ("main", "fix"):
        text = render(g)
        p = DATA / f"{g}.csv"
        if check:
            if not p.is_file() or p.read_text(encoding="utf-8") != text:
                sys.exit(f"{p} is out of date: run build.py build")
        else:
            p.write_text(text, encoding="utf-8", newline="\n")
    print("ok" if check else "built data/main.csv and data/fix.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("import")
    i.add_argument("--source", required=True, type=Path, action="append", help="folder of run folders; repeatable")
    i.add_argument("--only", help="import just this run id, leaving the others' recorded evidence untouched")
    b = sub.add_parser("build")
    b.add_argument("--check", action="store_true")
    ns = ap.parse_args()
    do_import(ns.source, ns.only) if ns.cmd == "import" else do_build(ns.check)
