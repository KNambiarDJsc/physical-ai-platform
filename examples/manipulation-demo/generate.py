"""Generate the SYNTHETIC warehouse pick-and-place demonstration dataset (seeded, deterministic).

    python examples/manipulation-demo/generate.py            # write data/baseline.csv, data/candidate.csv
    python examples/manipulation-demo/generate.py --check    # exit 1 if the committed files differ

Every row is synthetic: no robot produced it. The mapping labels it `evidence_class: synthetic`, which the platform
carries into every episode, result and report. Its purpose is to exercise the real evaluation pipeline (OpenMHS
verifier and release comparison) on data with known structure, not to describe any real system's performance.

Structure: 40 scenarios (SKU x pick location) x 3 attempts per release, two sites, three robots. Per attempt, one
of these ground-truth cases is drawn with release-specific probabilities:

  success       robot reports success; bin scale gains the SKU mass; vision sees the item in the bin
  missed_grasp  robot reports failure; scale and vision see nothing
  drop          robot reports success; item fell during transfer: scale and vision see nothing (contradiction)
  assist        robot reports success; an operator helped: scale and vision see the item, operator_assist = true
  scale_missing robot reports success; the scale reading is missing (blank cell)
  scale_bad     robot reports success; the scale flags its reading BAD
  late_reading  robot reports success; the scale reading arrives 9 s after the report (outside the window)
  timeout       robot reports timeout; nothing in the bin

The candidate grasps better (fewer missed grasps) but drops more items, so its REPORTED success rate rises while its
independently VERIFIED failure rate also rises. A handful of malformed rows show up in the validation report.
"""

from __future__ import annotations

import csv
import io
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLUMNS = [
    "episode_id", "robot_id", "site", "sku", "scenario", "start_time", "end_time", "robot_status",
    "bin_mass_delta_g", "bin_mass_quality", "bin_mass_time", "vision_in_bin", "vision_time", "operator_assist",
    "data_origin",
]  # fmt: skip
SKUS = {"sku-mug": 310, "sku-box-s": 120, "sku-bottle": 540, "sku-pouch": 95, "sku-can": 360}
LOCATIONS = ["shelf-a1", "shelf-a2", "shelf-b1", "shelf-b2", "tote-1", "tote-2", "tote-3", "tote-4"]
ROBOTS = {"site-east": ["arm-e1", "arm-e2"], "site-west": ["arm-w1"]}
CASES = ["success", "missed_grasp", "drop", "assist", "scale_missing", "scale_bad", "late_reading", "timeout"]
WEIGHTS = {
    "baseline": [0.70, 0.14, 0.04, 0.03, 0.03, 0.02, 0.02, 0.02],
    "candidate": [0.66, 0.05, 0.17, 0.04, 0.03, 0.02, 0.02, 0.01],
}
START = {"baseline": datetime(2026, 11, 2, 8, 0, tzinfo=UTC), "candidate": datetime(2026, 11, 9, 8, 0, tzinfo=UTC)}


def ts(t: datetime) -> str:
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def rows(release: str) -> list[dict[str, str]]:
    rng = random.Random(f"pap-demo-{release}-v1")
    t = START[release]
    out = []
    n = 0
    scenarios = [(sku, loc) for sku in SKUS for loc in LOCATIONS]
    for attempt in range(3):
        for i, (sku, loc) in enumerate(scenarios):
            site = "site-east" if i % 3 else "site-west"
            robot = ROBOTS[site][(i + attempt) % len(ROBOTS[site])]
            case = rng.choices(CASES, WEIGHTS[release])[0]
            n += 1
            start = t
            end = start + timedelta(seconds=round(rng.uniform(6, 14), 3))
            t = end + timedelta(seconds=round(rng.uniform(2, 6), 3))
            mass = SKUS[sku] + round(rng.gauss(0, 4), 1)
            placed = case in ("success", "assist", "scale_missing", "scale_bad", "late_reading")
            status = {"missed_grasp": "failure", "timeout": "timeout"}.get(case, "success")
            scale_t = end + timedelta(milliseconds=rng.randint(300, 1500))
            if case == "late_reading":
                scale_t = end + timedelta(seconds=9)
            row = {
                "episode_id": f"{release[:4]}-{n:04d}",
                "robot_id": robot,
                "site": site,
                "sku": sku,
                "scenario": f"{sku}@{loc}",
                "start_time": ts(start),
                "end_time": ts(end),
                "robot_status": status,
                "bin_mass_delta_g": ""
                if case == "scale_missing"
                else str(mass if placed else round(rng.gauss(0, 2), 1)),
                "bin_mass_quality": "BAD" if case == "scale_bad" else "GOOD",
                "bin_mass_time": ts(scale_t),
                "vision_in_bin": "true" if placed else "false",
                "vision_time": ts(end + timedelta(milliseconds=rng.randint(200, 900))),
                "operator_assist": "true" if case == "assist" else "false",
                "data_origin": "synthetic",
            }
            out.append(row)
    # Malformed rows the validation report must show (they are rejected, never silently dropped).
    bad1 = dict(out[0], episode_id=f"{release[:4]}-bad-status", robot_status="crashed?")
    bad2 = dict(out[1], episode_id=f"{release[:4]}-bad-time", end_time="2026-11-02 09:00:00")  # no UTC offset
    bad3 = dict(out[2], episode_id="", robot_status="success")  # missing episode id
    return [*out, bad1, bad2, bad3]


def render(release: str) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows(release))
    return buf.getvalue()


def main() -> int:
    data = HERE / "data"
    data.mkdir(exist_ok=True)
    stale = []
    for release in ("baseline", "candidate"):
        text = render(release)
        path = data / f"{release}.csv"
        if "--check" in sys.argv:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(path.name)
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path} ({text.count(chr(10)) - 1} data rows)")
    if stale:
        print(f"out of date: {stale}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
