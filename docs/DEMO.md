# Demo runbook (about 12 minutes)

> The laboratory-experiment demo (agent-assisted, 10 minutes, with the guided journey) is in `docs/demo/RUNBOOK.md`.

## Before you start

```bash
bash scripts/demo_up.sh          # starts the stack, seeds the demo workspace, opens the app (about 2 minutes)
```

Sign in at http://127.0.0.1:3000/settings as **ada** (admin), **bob** (engineer) or **vic** (viewer); workspace `demo`.
Keep ~2 GB of RAM free if you will run the live Gazebo simulation (it is optional; the recorded runs are real too).

## The story

*One platform, different environments, shared execution and evidence.* A change to a robot's software has to be proven,
not assumed. The platform runs the change in simulation, has an engineer approve what runs, judges every run with an
independent verification engine, and shows the evidence in 3D.

## Walkthrough

1. **Release Intelligence** (Releases): the real OpenAMRobot command-loss regression (#79). Pre-fix: the base drives on
   about 1 m after its commands stop. Fix: about 0.08 m. Show the engine's per-episode verdicts and the comparison:
   **insufficient evidence**. Say it plainly: a few runs cannot prove a regression, and the platform refuses to pretend.
2. **Digital twin**: open the pre-fix recording on upstream's robot model; scrub to the red "base still moving" event;
   **Explain this event** (cites stored evidence, says what is not known). Then **Compare with** the fix recording:
   the fix appears as a ghost, aligned at command loss, the two bases drift apart.
3. **Experiments** (the Studio): open *Stop on command loss*. Show the setup in words (baseline vs candidate), the
   finished run (verdict per trial from the engine, raw values side by side) and **Release verdict** (engine: insufficient
   evidence for 3 trials each; run again to add trials). A violated trial is *one contract violation*, not a regression.
4. **Approval**: as ada, **Ask to run** version 1; note ada cannot approve her own request. Sign in as bob (Settings),
   open the request, **Approve**. Trials run; open one in the twin.
5. **Live Gazebo** (optional, ~2 minutes per run): new experiment on *Gazebo: OpenAMRobot*, wiring `main` vs `fix`,
   1 repetition, rule "travel after kill is at most 0.15", approve as bob. Real headless Gazebo runs in WSL; the same
   journey ends in the twin. If memory is short the host refuses and says why; that is a feature.
6. **Workflows**: *Dispense 50 µL and verify* across the virtual lab's pump and balance; the balance reading is the
   independent evidence, the engine judges it. Show **Compose a workflow from instruments**.
7. **Agent tools** (if asked): the assistant is rule-based and read-only; the optional Strands harness uses a model the
   organisation provides, with a spend cap and a full trace, and can only *request* runs for a person to approve.

## What to say, and not say

- Every verdict is the OpenMHS engine's; the platform computes no statistic.
- Commands go only to simulated environments (the operator decides); physical equipment is read-only.
- Simulated evidence is labelled as such everywhere.
- The self-test host is a small kinematic model, not a simulator; the Gazebo runs are real.
- Do not claim general agent quality: the harness was verified with one real model on a small data set (safe, grounded
  behaviour there, nothing broader). It is a command-line component, not a page in the web app.
- Do not claim hardware validation or customer results; there are none (see `harness/blockers.md`).
