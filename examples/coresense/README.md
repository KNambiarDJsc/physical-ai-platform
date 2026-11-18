# Real robot evidence: CoreSense drone flights (Milestone B)

The first evaluation of **real, recorded robot data** through the platform (API, worker, pinned OpenMHS engine).
Evidence class: `physical` (real robots in a test facility, not a production deployment).

## Result

| Flight condition | GoTo goals | Robot reported failed | Verified failed: pose outside ±0.20 m of the waypoint at the claim | Supported success | Contradiction |
|---|---|---|---|---|---|
| no failure (nominal) | 35 | 0 of 35 waypoints | **31 of 35 waypoints (88.6 %)** | 4 | 31 |
| panel failure (induced) | 39 | 0 of 35 | 31 of 32 known (96.9 %), 3 unknown | 2 | 34 |
| double failure (induced) | 41 | 0 of 35 | 32 of 34 known (94.1 %), 1 unknown | 3 | 33 |

Counts are per waypoint (the engine counts repeated attempts at a waypoint as one scenario, judged by majority);
goal counts are per GoTo action. All figures are engine outputs from `results/*/report.json`.

**What the platform concludes:** for both comparisons (nominal vs. panel failure, nominal vs. double failure) the
engine reports **insufficient evidence** of a change, both for the robot's own reports (no failures at all, so
nothing to compare) and for the independent evidence (both conditions mostly fail the contract; the 95 % interval
of the difference spans no change). That is the correct answer for these sample sizes.

**What the data shows within each condition:** the drones reported every GoTo they finished as `SUCCEEDED`, yet at
the moment of that claim the motion-capture pose was outside a ±0.20 m box around the waypoint about nine times in
ten. This does **not** show that the drones miss waypoints: an earlier OpenMHS study of the same bags found they
reach the waypoint (median 2.3 cm) about 0.5 s *after* claiming. The honest reading is that Aerostack2 declares
success before the pose is within 0.20 m of the waypoint as measured by motion capture, either early or with a
tolerance other than the published default. Which one cannot be decided from this dataset (see limits).

## Provenance

- Dataset: CoreSense Inspection Testbed ROSbag Dataset, Zenodo [10.5281/zenodo.23243295](https://doi.org/10.5281/zenodo.23243295),
  CC BY 4.0, Garcia Patino Lenza, Universidad Politecnica de Madrid. Three Crazyflie drones, Aerostack2, OptiTrack.
- Bags used: `rosbag2_real_paths_2_OK_{no_failure,panel_failure,double_failure}` (288 MB); their SHA-256, and the
  SHA-256 of each derived CSV, are in `data/provenance.json`.
- Reader: the pinned OpenMHS commit's own rosbag2/CDR reader (`.engine/src-<commit>/python/openmhs/importers`), used
  read-only; nothing in OpenMHS was changed.
- `extract.py` -> `data/*.csv` -> `mapping.json` (pap.mapping/1, `coresense-goto-mocap`) -> platform evaluation via
  `evaluate.py` -> `results/<baseline>__<candidate>/{report.json,report.html,validation.json}`.

## Accounting

- Episodes processed: **115 GoTo goals** (35 + 39 + 41) from 3 drones in 3 bags.
- Malformed or incompatible rows: **0** rejected by the mapping (validation.json).
- Goals without a terminal status: 0. Goals whose waypoint could not be joined: 0. Goals without a motion-capture
  sample within 50 ms of the claim: 0 (largest gap 5.9 ms).
- Reported outcomes: 107 `SUCCEEDED`, 8 `CANCELED` (waypoint re-assigned by the swarm's auction after an induced
  failure), 0 `ABORTED`.
- Takeoff and Land goals, the mission-level outcome and the swarm's fault facts are in the bags and handled by the
  OpenMHS importer, but are **not** evaluated here (one task type per comparison; GoTo is the claim being tested).

## Verification rule applied

`goto-arrived-at-waypoint`: x and y of the OptiTrack pose each within ±0.20 m of the waypoint, from the pose sample
nearest the claim time, no further than 50 ms from it. The same box and window as the OpenMHS CoreSense verifier,
with one difference: the platform evaluates the **single nearest sample**, the OpenMHS verifier **every sample** in
the window. On these bags the nearest-sample rule finds 9 of 107 claimed arrivals inside the box, the
every-sample rule 4 of 107. Both say the same thing; the numbers differ and both are stated.

## Claims this evidence cannot support

- **No software comparison.** The dataset names no software revision: the "releases" are flight conditions of the
  same software. Nothing here says one Aerostack2 version is better than another.
- **The 0.20 m tolerance is an assumption.** It is Aerostack2's `go_to_threshold` default; the flights' own
  configuration is not published. A different tolerance is a different contract and gives different numbers.
- **The reference is not fully independent.** The OptiTrack pose that verifies the claim also feeds the drone's
  controller. A localisation fault would affect both.
- **Failures were induced** by the experimenters; they say nothing about how often such failures occur.
- **Clock.** Times are the recorder's receipt times on one host clock (assumed; the dataset does not say).
- **Sample size.** 35 waypoints per condition: enough to see the gap between reported and verified outcomes, not to
  detect a modest difference between conditions.

## Integration effort

About two hours of engineering, of which most went into understanding the data, not into code:
`extract.py` (about 150 lines, reusing the OpenMHS reader), `mapping.json` (40 lines), a new `physical`
evidence class (lab flights are neither simulated nor production), and two platform defects the data exposed and
that were fixed first:

1. A **cancelled** goal was counted as a failure claim, so cancelled goals the drone happened to be near showed as
   contradictions. Cancellation claims nothing; the evidence alone now classes it (`test_outcome_class_table`).
2. The `physical` evidence class did not exist; the only honest label for these flights was missing.

## Reproduce

```bash
bash scripts/build-openmhs.sh                     # pinned engine and its source (reader)
uv run python examples/coresense/extract.py /path/to/coresense/bags   # data/*.csv + provenance.json (compare its digests)
uv run python scripts/dev_stack.py --api-port 8765 &                  # or the Compose stack
uv run python examples/coresense/evaluate.py --api http://127.0.0.1:8765 --baseline no_failure --candidate panel_failure
```

Two runs of the same evaluation give identical counts, rates, intervals, verdicts and episode classes; only the
engine's incident ids differ, because they are derived from the organization each run creates. Within one
evaluation the JSON report is byte-identical on every download.
