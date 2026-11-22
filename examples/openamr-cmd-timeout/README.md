# Command-timeout regression (openamr-platform-sw #79, PR #177), recorded

**Simulated evidence (Gazebo).** The base is driven at 0.2 m/s, its command source is killed, and the distance it still
travels is measured from Gazebo's own world pose. Upstream's test allows 0.15 m (`MAX_TRAVEL_AFTER_KILL_M` in
`test_sim_cmd_vel_timeout_gazebo.py` at 505d17a); that is the contract here.

| Arm | Runs | Travelled after the kill |
|---|---|---|
| main (69847ab wiring, no timeout) | 5 | 0.997 to 1.003 m: the base drives on |
| fix (#79, 0.2 s timeout) | 7 | 0.073 to 0.085 m |

What the engine says: each run is judged individually (5 verified failures, 7 verified successes), and the comparison is
**insufficient evidence**: 5 and 7 runs are far below the 30 known outcomes per arm its rules need. That is the result,
not a defect, and it is not tuned away.

Honest limits:
- 10 of the 12 runs come from the user's own scripts of 2026-11-20 (`runs.json` says for each run why it is labelled
  main or fix). Only three runs are exactly on the committed software (two on the fix 505d17a, one the pre-fix arm described below); the others ran on the branch's working tree
  minutes before the commit. `software_exact` says which.
- Procedures differ: killing the publisher, or killing a downstream node (collision monitor, velocity smoother) while the
  source keeps publishing. `site` carries the procedure so the strata keep them apart.
- Times are the result files' modification times (1 s resolution), not simulation time.
- No controller report exists for these runs, so the reported outcome is unknown and only the measurement judges.

Files:
- `recorded/<run>/` the original result files (sha256 in `runs.json`); two runs (one per arm, recorded 2026-11-21 and
  2026-11-22) also have their identity file, MCAP bag and bag summary. The pre-fix bag's `/clock` is not monotonic (two
  sources interleaved for about 1.6 s of a 17.8 s recording); the summary and the twin report it instead of hiding it.
- `model/` upstream's OpenAMRobot platform model (expanded xacro, 10 visual STL meshes, NOTICE and LICENSING), copied
  unchanged by `model/build.py`; `build.py --check` there verifies it. Licence: CERN-OHL-P-2.0 (see its NOTICE.md).
- `data/main.csv`, `data/fix.csv` built from `recorded/` by `build.py build` (`--check` verifies them).
- `mapping.json` the evidence mapping and contract.
- `scenario/run_main.sh` the pre-fix arm: it puts the two wiring files back to origin/main for one run and restores them
  (it refuses to start on a dirty checkout, and the run's identity records the dirty tree and the files).
- `scenario/run_scenario.sh` one more run, inside WSL with the openamr-platform-sw workspace built. **Not part of the
  platform**: the platform never starts it and never publishes to a ROS topic.

Checked by `services/api/tests/test_ros_regression.py` (real pinned engine, reports byte-identical twice).
