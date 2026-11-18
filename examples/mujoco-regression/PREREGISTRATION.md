# Pre-registration: controlled regression experiment (Milestone C)

Written and committed **before** any held-out episode was run. The held-out seeds (A/B/D: 1000-1149, C:
5000-5149) had never been simulated when this file was committed; the git history shows the order.

## Question

Does the platform, with the pinned OpenMHS engine, (1) detect a known physical regression, (2) report a
smaller one with appropriate uncertainty, (3) keep the robot's self-reports apart from independently measured
outcomes when they disagree, and (4) avoid an unsupported regression verdict when nothing changed?

## Task and measurements (fixed in `sim.py`, Config hash recorded per group)

- Planar two-link arm in MuJoCo 3.17.0, CPU only, headless, 2 ms physics step, 100 Hz controller.
- Each episode: start pose and target drawn from the seed alone (same seed, same setup in every group).
- Controller: smooth joint-space trajectory over 1 s to the target (nominal-model IK), PD torque control.
- **Robot self-report** (what the robot claims): from quantized joint encoders (4096 counts/rev) through its
  nominal kinematic model (links 0.300/0.250 m): `succeeded` when its estimate is within 2 cm of the target and
  the joints are still (< 0.2 rad/s) for 10 control periods after the move; `timeout` after 3 s otherwise.
- **Independent measurement**: the simulator's ground-truth fingertip position at the time of the report. The
  real links are 0.303/0.247 m, a calibration error the robot does not know about, identical in every group.
- **Verification rule** (mapping contract): fingertip within 0.02 m of the target at the report time.

## Groups

| Group | Controller | Seeds | Role |
|---|---|---|---|
| A | baseline, 10 ms command latency | 1000-1149 | baseline |
| B | 50 ms command latency | 1000-1149 (paired with A) | primary regression, declared before the pilot |
| C | baseline, 10 ms | 5000-5149 (independent) | no-change control |
| D | 20 ms command latency | 1000-1149 (paired with A) | secondary regression, **chosen on the pilot** |

Latency is applied in whole control periods (10 ms), so 20 ms is the only setting between the baseline and 50 ms.

## Pilot (seeds 900000-900029, never reused)

Used for runtime, memory, variability and two corrections, all made before this file:
- The memory probe read 0 MB on Windows (untyped ctypes handle): fixed; real peak about 57 MB.
- The baseline's stillness threshold (0.05 rad/s) was below one encoder count per control period (0.153 rad/s),
  so the baseline reported `timeout` in 25/30 pilot episodes although the fingertip was within 2 cm in all 30:
  raised to 0.2 rad/s. This is a fix to the baseline controller, applied to every group.
- After the fix (30 pilot episodes per setting): latency 10 ms: 1/30 reported not succeeded, 0/30 fingertip
  outside 2 cm; 20 ms: 30/30 reported not succeeded, 5/30 outside; 30 and 40 ms: 30/30 and 27/30; 50 ms: 30/30
  and 28/30. D = 20 ms was chosen from this sweep, on pilot seeds only.

## Sample size

Primary endpoint: the **independently verified failure rate** (fingertip outside 2 cm at the report).
Minimum detectable effect: +15 percentage points. Two-sided alpha 0.05, power 0.80, normal approximation for
two independent proportions. Baseline planning rates p0 = 0.05 and 0.10 (pilot: 0/30, rule-of-three upper bound
0.10) give 76 and 100 per group. **n = 150 per group**: the larger estimate plus a buffer for the engine's
Newcombe interval (more conservative than the normal approximation) and its 0.01 no-change margin. Cost is about
2 s of CPU. The number was not chosen by looking at any held-out result.

## Analysis (all statistics by the pinned engine; no separate statistics in Python)

Platform evaluations, each with the same mapping revision and `min_known` 30, `margin` 0.01, one site:
1. A vs B, paired by scenario (= initial condition).
2. A vs D, paired by scenario.
3. A vs C, unpaired (different initial conditions).

## Predictions, recorded before running

| Comparison | Reported (robot) | Verified (independent) |
|---|---|---|
| A vs B | regression | **regression** |
| A vs D | regression (robot reports nearly all timeouts) | regression, smaller effect (pilot 5/30); a wide interval |
| A vs C | no_change or insufficient_evidence | **no_change or insufficient_evidence** |

Outcome classes: D will have many **contradictions** (robot reports timeout, fingertip within 2 cm); A and C few,
from the calibration error near the 2 cm boundary.

A `regression` or `improvement` verdict for A vs C is a **false positive** and will be reported as such. Any
prediction that fails is reported as failed, not explained away.

## Resource limits

CPU only, no rendering, one process; peak memory checked after every episode against a 400 MB budget, and the
run stops with the measurement if it is exceeded.
