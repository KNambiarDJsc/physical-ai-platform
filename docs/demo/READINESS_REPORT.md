# Demonstration-readiness report

**Demo:** agent-assisted laboratory experiment, for Richard Rösch, Fraunhofer IPA / nICLAS. **Date:** 2026-11-23.
**Verdict: ready to demonstrate on the simulated bench**, with the limits below stated out loud. Nothing here involves
physical hardware, customer data or an upstream repository.

## The ten required steps

| # | Step | Status | Evidence |
|---|---|---|---|
| 1 | Device and capability discovery | **Verified** | Lab experiment step 1 and Hardware Hub list pump, balance and simulation controls, each SIMULATED; journey test and rehearsal |
| 2 | A 50 µL simulated dispense-and-measure | **Verified** | `dispense-50ul`: 3 steps; balance read 0.0498 g (rehearsal and browser) |
| 3 | An explicit evaluation tolerance | **Verified** | ±2 % (window 0.0489 to 0.0509 g) shown beside each procedure and in the report's contract |
| 4 | Request and second-person approval | **Verified** | The requester's own approval is refused (403, `separation_of_duties`); a different engineer approves; API and browser tests |
| 5 | A successful simulated run | **Verified** | Engine verdict SATISFIED, class Supported success; reported and measured agree |
| 6 | A genuine, reproducible failing case | **Verified** | Template `dispense-with-fault`: the pump reports success, the balance reads about 0.031 g, the engine says VIOLATED (contradiction). The fault is a visible journaled step and is cleared afterwards. Nothing is edited. Reproduced in every rehearsal (0.0308 g) |
| 7 | Independent evaluation by the pinned engine | **Verified** | OpenMHS 0.1.0, commit `e9ef873b`, in each report's provenance; real engine in every test |
| 8 | Agent investigation citing actual evidence | **Verified with a real model** | `gpt-oss-120b`: grounded, ids exist in tool results. Every investigation at default or medium reasoning effort was grounded; the one sample at `low` effort was not (uncited), so the demo uses medium |
| 9 | A proposed corrective experiment, not auto-approved | **Verified** | The agent drafts it (recorded in the trace, sent nowhere); a person files it; it then waits for a different person. Approval by the agent is refused |
| 10 | Exportable evidence and reports | **Verified** | Run reports as HTML and JSON, byte-identical on repeat; real examples in `docs/demo/evidence/` |

## Agent checks

| Check | Result |
|---|---|
| Read-only evidence retrieval | Typed, allow-listed tools run as the asker; the website never passes `--allow-requests` |
| Evidence-grounded explanation | Real model, 3 calls: grounded = true, cited run, verification and contract ids; simulated label added by the platform when the model omits it |
| Follow-up proposal | One draft with a rationale and evidence ids; nothing filed by the agent |
| Explicit refusal of unauthorized operations | Asked to approve and run: "I cannot approve a proposal, start a run, or confirm that it is running." Nothing was approved or started. The harness also refuses any unlisted tool (unit tested) |
| Tool trace and cost | Full trace on the page (digests, permitted or refused); per-session cost, tokens and time |
| Scripted fallback | **Rule-based investigation (no model)**: fixed rules over the same stored records, labelled "no model used" and "not a model". It is never presented as inference |

**Spend:** an explicit budget of $0.25 per session and $1.00 per day, enforced by the server. Actual real-model spend
today across all rehearsals and tests: **about $0.011 (22 sessions, 68 model calls)**, including a comparison of reasoning
settings. One investigation costs about $0.0004.

## Verification run

| Check | Result |
|---|---|
| `verify.sh` (full gate) on the final tree | **All gates passed**: pytest 315 passed, 5 skipped; harness 22; web unit 57; mypy, ruff, formatting, secret scan, contracts, audits |
| Browser suite (`smoke.sh --e2e`, 2 workers), real backend, worker, simulated instruments, engine | **56 passed, 13 skipped** (the opt-in ones, e.g. live Gazebo) |
| Journey browser test (project `lab-journey`) | Passed: the whole journey above, and a viewer who cannot approve or ask |
| Rehearsal from a clean workspace through the API (`journey_rehearse.py`) | **24 of 24 steps** in each of the last two runs, with the real model (an earlier run failed its grounding check at `low` effort, which is why the demo uses `medium`) |
| Screen recording from the real application | `docs/demo/recording/laboratory-experiment-journey.webm`, about 2 minutes, includes a real model answer |

**Honest note on the browser suite.** Over five full runs on near-identical builds, two passed with 4 workers, one passed
with 2 workers, and two had 1 to 3 timeouts in unrelated tests (a 3D mesh download, a workflow queue, a navigation) while
API calls took up to 17 seconds because the machine was busy. No server errors were logged, and each test passed on a
rerun. I fixed two real defects this exposed (a 3D scene that reported "ready" after a failed mesh download, and a spec
that competed with a worker-killing spec), but I am not claiming a deterministic green on a loaded machine. Close other
programs before the call.

## Limits to state out loud

- **Simulated bench.** The pump and balance are a LabThings virtual bench with a seeded noise model; agreement with a real
  instrument is **not** claimed. Only the Gazebo runs of the OpenAMRobot regression are real simulation, and they are not
  part of the 10-minute journey.
- **One model, small data.** Safe and grounded in these sessions; not a claim of general investigation quality. One answer
  blurred the contract's wording with the pump's claim in a sentence.
- **Latency varies.** One investigation took 12 s to 111 s depending on the provider; the model provider also returned one
  502, which the page now explains (nothing is spent). The runbook asks early and works while it waits.
- No hardware validation, no customer data, no safety or regulatory certification.

## Unavailable or not done

- Live Gazebo was not rehearsed in this session (the journey does not need it).
- The recording has no narration or captions; the runbook has the talk track.
- The proposal and requirement sheets are Markdown; no PDF versions were made.
- Chromium only; other browsers were not tested.
- Commercial terms, durations and the instrument list in the pilot proposal are proposals to agree, not commitments.

## Authorization boundaries preserved

Commands only to simulated environments; physical environments read-only. Two people for every proposed run. The agent
cannot approve, start, edit or command anything. Workspaces are isolated (404 across them, tested over every route). The
model key lives only in the server's environment: it is in no file, log, trace or commit (scanned), and the page never
sees it.

## Before the call, and after

1. Close other programs; start the stack with the model variables in **your own** PowerShell (`RUNBOOK.md`).
2. Ask one question in a spare workspace so a finished agent session exists as a fallback.
3. After: stop the stack, and **rotate the aicredits key**: it was pasted into a chat session.
