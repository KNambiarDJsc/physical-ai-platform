# The 30-minute exercise

You will answer the same release-evaluation questions twice: **Part A** with the platform (about 21 minutes) and
**Part B** with a plain Python script (about 9 minutes), then fill in [FORM.md](FORM.md). Please time yourself
honestly; slow steps and confusing steps are exactly what we want to hear about.

Before you start: the platform is running (`bash trial/start.sh`, see [README.md](README.md)) and you are in the
repository folder. **Do not open `trial/expected.json`** until you have finished: it is the answer key.

Write your answers in the form as you go. A task is "complete" when your answer matches the check in the last
column of its table; if it does not, write down what you got instead (that is useful, not a failure).

## The data (two datasets, deliberately different)

| | MuJoCo reaching arm | CoreSense drone flights |
|---|---|---|
| What it is | A **simulation** we generated: a planar two-link arm reaching a target | **Real recorded flights** of three Crazyflie drones (public dataset, CC BY 4.0) |
| The robot's own claim | its controller's report: succeeded or timeout | the drone's own GoTo action status |
| The independent evidence | the simulator's true fingertip position | a motion-capture pose at the moment of the claim |
| "Verified failure" means | fingertip more than 2 cm from the target | pose outside +-0.20 m of the waypoint |
| Files | `examples/mujoco-regression/data/{A,C,D}.csv` | `examples/coresense/data/{no_failure,panel_failure}.csv` |
| Mapping (column description) | `examples/mujoco-regression/mapping.json` | `examples/coresense/mapping.json` |

In the MuJoCo data, **A** is a baseline controller (10 ms command latency), **D** the same controller with 20 ms
latency (the regression we injected), and **C** the baseline controller run again on different initial conditions
(a control: nothing changed). Each file has 150 episodes.

## Part A: with the platform (about 21 minutes)

Open http://127.0.0.1:3000 and sign in on the **Settings** page with any name.

| # | Task | Do | Record | Complete when |
|---|---|---|---|---|
| T1 (3 min) | Workspace | **Overview**: create an organization (any name and slug) and a project with slug `reach`; open the project. | Time taken. | You are on the project page. |
| T2 (6 min) | Compare baseline and 20 ms regression | Add three releases named exactly `latency-10ms`, `latency-20ms`, `latency-10ms-rerun`. Upload `A.csv`, `C.csv`, `D.csv`. Paste the whole of the MuJoCo `mapping.json` into the mapping box and add it. Under **New evaluation** choose baseline `latency-10ms` with evidence `A.csv`, candidate `latency-20ms` with `D.csv`, the mapping, task type `reach`, tick **Also pair by scenario**, and start it. Wait for it to finish. | The verdict for **Reported by the robot** and for **Independently verified**; the number of verified failures in the candidate; the number of **Contradiction** episodes in the candidate. | Both verdicts are read correctly; the counts are the ones the page shows. |
| T3 (3 min) | Explain one failure | Click **Inspect episodes**, pick **Verified failure** in the Outcome filter, open any episode. | What the robot reported; the measured fingertip error; which condition failed. | You can say, from the page alone, why this episode counts as a failure. |
| T4 (3 min) | Did nothing change? | New evaluation: baseline `latency-10ms` (`A.csv`) against candidate `latency-10ms-rerun` (`C.csv`), task type `reach`, **not** paired. | Both verdicts and the reason text the page gives. | Both verdicts and the reason are recorded. |
| T5 (4 min) | Real robot data | Back on **Overview**, create a second project (slug `drones`). Add releases `condition-no_failure` and `condition-panel_failure`, upload the two CoreSense CSVs, add the CoreSense `mapping.json`, evaluate with task type `goto`, paired. | Both verdicts; the evidence label shown at the top of the result; the number of **Contradiction** episodes in the baseline. | Verdicts, label and the count are recorded. |
| T6 (2 min) | Reproducibility | On the MuJoCo comparison from T2 click **Download JSON report** twice, and compare the two files' SHA-256 (`sha256sum f1 f2` or `Get-FileHash`). Click **Download HTML report** and open it. | Whether the two hashes are identical; which engine commit the HTML report names. | You have a yes/no and a commit hash. |

Hints that are not spoilers: the first evaluation takes about 10 seconds; if you get stuck for more than two
minutes, write down where and move on (the time you lost is data).

## Part B: the same questions with a plain script (about 9 minutes)

The script `trial/baseline/analysis.py` is our own conventional baseline: standard-library Python, reading the
**same raw CSVs**, applying the **same definitions** (see the table below). It stands in for the analysis you
would otherwise write. If you would rather do Part B with your own tools (pandas, a notebook, a spreadsheet),
please do, and say so in the form.

| # | Task | Do | Record |
|---|---|---|---|
| S1 (3 min) | Same comparison as T2 | `python trial/baseline/analysis.py mujoco A D` | Time to a result (including reading the output); do the verdicts and counts agree with T2? |
| S2 (2 min) | Same as T4 | `python trial/baseline/analysis.py mujoco A C` | Same questions. |
| S3 (2 min) | Same as T5 | `python trial/baseline/analysis.py coresense no_failure panel_failure` | Same questions. |
| S4 (2 min) | Explain one failure | Without the platform's episode view: find, in `D.csv`, one episode that fails the 2 cm rule, and say what the robot reported for it. | Time taken; how you did it. |

### The two workflows are meant to be equivalent

| Question | Platform | Script |
|---|---|---|
| "Failed" as the robot saw it | the robot's own status (not `succeeded`) | the same column, same rule |
| "Failed" as measured | the contract in `mapping.json` (fingertip error at most 0.02 m) | `float(tip_error_m) > 0.02` |
| Episode vs. scenario | the engine counts one scenario per initial condition, judged by majority | the same |
| Intervals and verdict | computed by the OpenMHS engine (Wilson, Newcombe, McNemar) | re-implemented in the script (standard formulas) |
| Cancelled goals (CoreSense) | claim nothing | the same |

A test in the repository (`services/api/tests/test_trial_baseline.py`) checks that the script reproduces the
engine's counts, intervals, verdicts and McNemar results on all five shipped comparisons. If your two answers
disagree anywhere, that is a finding: please write it down.

When you are done, fill in [FORM.md](FORM.md). Thank you.
