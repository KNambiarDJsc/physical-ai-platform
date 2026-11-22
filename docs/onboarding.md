# Onboarding a team

For a robotics or laboratory team using the platform for the first time, once it is installed (see
[deployment.md](deployment.md)). About an hour end to end.

## 1. Sign in and create the workspace

Sign in with your organisation's account. **Get started** creates the workspace and walks through connecting an
environment. Invite colleagues under **Settings** with a role:

| Role | Can |
|---|---|
| viewer | read everything in the workspace, propose a workflow run, ask for an experiment run |
| engineer | everything a viewer can, plus create workflows and experiments and approve or reject runs |
| admin | everything, plus members, service credentials and the workspace itself |

## 2. Connect an environment and discover

Pick an environment the installation offers (the operator's catalog). **Hardware Hub → Discover** lists its devices,
their readable properties and actions. Physical environments are read-only in the platform.

## 3. Run something verified

- **Workflows**: start from a template or **compose** one across instruments (for example tare, dispense, weigh), and say
  how the engine verifies it: whose report is the claim, which other step measures the outcome, and the conditions.
  Run it in the **Workbench**; the verdict (satisfied, violated, unknown) is the OpenMHS engine's.
- **Experiments**: pick a simulation environment and scenario, set a baseline and a candidate, how many repetitions and
  the pass rule, then ask for a run. Another engineer approves that exact version; trials run one after another.

## 4. Inspect and investigate

Open a trial's recording in the **Digital twin**: the robot model replays it, the timeline marks events by rule, and the
engine's verdict sits beside it. **Compare** puts a second recording on the same time axis as a ghost (baseline versus
candidate). **Explain this event** gives findings that cite the stored evidence and say what is not known.

## 5. Decide with evidence

A violated trial is one run breaking its contract. Whether a release regressed is a statistical claim: **Judge as
releases** (Experiments) or a **Release** comparison (uploaded evidence) asks the engine, which answers regression,
improvement, no change or insufficient evidence, with its reasons. Run more trials until it can decide.

## Bring your own evidence

Release Intelligence also works without a simulator: upload the recorded episodes of two releases (what the robot
reported and an independent measurement, as CSV or JSON), map the columns once, and evaluate. `trial/` holds a
30-minute exercise for that path.

## The assistant and the agent harness

The in-app assistant is rule-based and read-only. The optional agent harness (`docs/agent-harness.md`) uses a language
model your organisation provides, with a spend cap and a full trace; it can read and explain, and only record requests
for a person to approve.
