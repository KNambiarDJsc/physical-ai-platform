# Release Intelligence for physical AI: technical pilot brief

**Status: pre-pilot prototype. Not production-ready. No external team has used it yet.**

## The problem

When a robot's software or policy changes, the robot's own logs say whether it *thinks* it succeeded. They do not
say whether the task was actually done, or whether a measured difference between two releases is real or noise.
Teams answer this with custom scripts that are rarely reproducible and rarely separate what the robot claimed from
what was independently measured.

## What the prototype does

Given episodes from a baseline and a candidate release, each with the robot's reported outcome and an independent
measurement (simulator state, motion capture, a scale, a camera), it:

1. checks every reported outcome against the measurement, and keeps "reported" and "verified" apart;
2. asks the OpenMHS engine for a verdict with confidence intervals: regression, improvement, no change, or
   **insufficient evidence**. Unknown evidence is a first-class outcome and is never counted as success;
3. lets you open any episode to see the claim, the rule applied and the measured value;
4. records the engine build, the mapping and the input checksums, and exports an HTML and a JSON report that
   regenerate identically.

It is self-hosted (Docker Compose). The running system sends nothing off the machine. The statistics are computed
by the engine, not re-implemented by the platform.

## What we have shown, and how far it goes

| Evidence | Result | Reach |
|---|---|---|
| **Real flights** (CoreSense, 3 Crazyflie drones under motion capture, public CC BY 4.0 data), 115 GoTo goals | The drones reported every finished goal as succeeded; at the moment of the claim the motion-capture pose was outside the assumed 0.20 m box for about 9 in 10 waypoints. The engine finds insufficient evidence of a difference between nominal and induced-failure flights (35 waypoints per condition). | One real dataset. No software revision is published, so this is **not** a release comparison. The tolerance is an assumption and the reference pose also feeds the controller. |
| **Controlled simulation** (MuJoCo reaching arm), pre-registered, 600 episodes | A 50 ms command-latency regression: detected (+97.3 pp verified failures). A 20 ms regression: detected (+21.3 pp, interval +15.0 to +28.6), where the robot's own reports overstated it 4.5-fold (118 contradictions). An unchanged controller on new seeds: no regression verdict. | Simulation, written by us, one task. |
| **Defects the evidence exposed** | A cancelled goal was counted as a failure claim; lab flights had no honest evidence class. Both fixed. | Shows the method finds problems in the tool itself. |

Engineering state: the stack builds and runs from a clean checkout on a GitHub runner (non-root containers, worker
limits, security and dependency scans, browser tests including a killed and restarted worker); a pass through the
trial exercise is recorded in `DRY_RUN.md`.

## What it cannot do yet

- **Only pass/fail rates are compared (G-7).** A 3.6-fold loss of accuracy in the simulation showed up only as
  marginal misses; a regression in margin is invisible until it becomes failures.
- **"No change" cannot be established for a very reliable baseline (G-8).** The honest answer is "insufficient
  evidence", not "nothing changed".
- Input is CSV or JSONL with a hand-written mapping; ROS bags, MCAP and LeRobot data need a conversion script.
- It needs an independent measurement. Without one, outcomes are "reported only".
- Development identity in the trial; OIDC sign-in is tested only against a local test provider; no backup tooling
  or metrics dashboards; several navigation pages are placeholders. See `LIMITATIONS.md`.

## What a pilot would involve

You provide: two releases' episodes as CSV or JSONL; a reported outcome per episode; at least one independent
measurement per episode; and the rule that decides success. We help write the mapping. Your data stays on your
machine. We would like to learn whether the verdicts and the reported-versus-verified split change what you would
conclude on a real release, and where a plain script serves you better. We do not know yet whether they do.

## How to evaluate it without a commitment

`trial/` holds a 30-minute exercise with a published answer key, a plain-Python baseline doing the same analysis,
and an evaluation form. It runs on your own machine with no credentials of ours.

Contact: *(to be added by the project owner)*
