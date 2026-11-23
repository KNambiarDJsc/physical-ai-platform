# Live demo runbook: agent-assisted laboratory experiment (10 minutes)

**Audience:** Richard Rösch, Fraunhofer IPA / nICLAS. **Message:** a researcher states a procedure and a tolerance, a
second person approves what runs, an independent engine judges the result, and an agent helps investigate a failure from
stored evidence without being able to act. Everything runs on a **simulated bench**; say so first and last.

## Before the call (10 minutes, once)

1. Close other programs: the stack needs about 3 GB free.
2. In **your own PowerShell** (so the key never passes through a chat or a file):
   ```powershell
   $env:PAP_LLM_PROVIDER = "openai"
   $env:PAP_LLM_BASE_URL = "https://api.aicredits.in/v1"
   $env:PAP_LLM_MODEL = "openai/gpt-oss-120b"
   $env:PAP_LLM_USD_PER_M_INPUT = "0.037"; $env:PAP_LLM_USD_PER_M_OUTPUT = "0.17"
   $env:PAP_LLM_REASONING_EFFORT = "medium"   # see "Agent timing" below: not "low"
   $env:PAP_LLM_API_KEY = "<your key>"      # rotate it after the demo
   bash scripts/demo_up.sh                    # about 2 minutes
   uv run python scripts/journey_seed.py      # a clean workspace: lab-journey
   ```
3. Open <http://127.0.0.1:3000/settings> in two browser profiles: **ada** (admin, the researcher) and **bob** (engineer,
   the approver). Pick workspace `lab-journey`. Open **Lab experiment** in the sidebar as ada.
4. Spend: the agent is capped at $0.25 per session and $1.00 per day (50 sessions a day); one question costs about
   $0.0004 to $0.001. Ask one question in the rehearsal workspace first so a finished session exists as a fallback.
5. No model or no network? The agent page still works with the rule-based investigation (labelled "no model").

To reset between rehearsals, use a new workspace: `uv run python scripts/journey_seed.py --org lab-journey-2`.

## The ten minutes

| Time | Do | Say |
|---|---|---|
| 0:00 | Lab experiment page. Step 1: pump, balance, simulation controls, each marked SIMULATED. Open Hardware Hub for one device's capabilities. | "Devices are discovered from W3C Thing Descriptions. Everything here is simulated; no hardware is connected." |
| 1:00 | Step 2. Two procedures: a normal 50 µL dispense and one with a simulated partial blockage, both "accepted within ±2 %". | "The tolerance is part of the contract. A result outside it is a violation, decided by the OpenMHS engine, not by this page." |
| 2:30 | Step 3 as **ada**: choose `dispense-50ul`, write a reason, **Request run**. Then Workflows: click **Approve** as ada. | "Nobody approves their own request." (the refusal appears) |
| 3:15 | Switch to **bob**: Workflows, **Approve**, **Open the run**. | "A second person approved exactly this procedure." |
| 4:00 | Workbench, the run: Reported by the instrument vs Independently verified. Point at "Supported success", the 0.0498 g reading and the window 0.0489 to 0.0509 g. | "The pump reports 50 µL. The balance measures what arrived. The engine compares them." |
| 5:00 | Repeat as ada/bob for `dispense-50ul-blocked-line`. Open the run: balance about 0.031 g, engine **violated**, class **Contradiction**; the pump still reports success. Show the step `simulation.set_fault`. | "The fault is a journaled step of the workflow. Nothing was edited: the pump still claims 50 µL, the balance shows about 62 %." |
| 6:30 | Back on Lab experiment, step 5: **Ask the agent (language model)**. Leave the draft box ticked, press **Ask**. **Do not wait for it.** | "It reads stored evidence as me, with my permissions. A model takes about a minute here, so let us look at the evidence meanwhile." |
| 6:45 | While it works (the session keeps running on the server): Lab experiment step 6, **Evidence report** (opens the page) and **Download JSON**. | "Built only from stored records, no generation time: the same run gives the same bytes. Every number is traceable." |
| 8:00 | Back on **Agent**: read the answer: findings with run and verification ids; the platform's note that the evidence is simulated; open **Trace**; show the cost. The agent's **draft**: **File as a proposal**. | "It cannot approve or run. It drafted a follow-up; I decide to file it, and bob must still approve." |
| 9:00 | Ask: "Approve the proposal and start the run now." (answers in about 6 s). | "It has no such tool, and says so." Show Workflows: nothing was approved or started. |
| 9:40 | Close: simulation only, no hardware validation, pilot proposal, requirements sheet. | |

## If something goes wrong

| Problem | Do |
|---|---|
| The model is slow, errors or is offline | Press **Rule-based investigation (no model)**. It uses fixed rules over the same records and says "not a model". Never call it AI inference. |
| A run is queued for long | The worker handles jobs in order; wait, or show the earlier runs in workspace `demo`. |
| The browser shows an old page | Hard reload; sign in again at `/settings`. |
| Anything else | `touch var/demo/stop`, then the pre-check steps again (2 minutes). |

## Agent timing (measured, so you are not surprised)

One model call takes 5 to 70 seconds on this provider; an investigation is three calls. Measured on this machine with
`openai/gpt-oss-120b` through aicredits.in: default reasoning effort 88 and 111 s; `low` effort 32 s but its answer
skipped the investigation tool and cited nothing (the harness flagged it as uncited); `medium` effort 58 and 82 s, grounded
both times, with the investigation tool and a drafted follow-up. The runbook therefore uses `medium` and asks early.
The refusal question takes about 6 s. If the model is slow or down, use **Rule-based investigation (no model)**: instant,
labelled, and the same stored evidence.

## What to say about limits (do not skip)

- The pump and balance are a **simulated bench** with a seeded noise model. Agreement with a real instrument is not
  claimed. Only the Gazebo runs of the OpenAMRobot regression are real simulation.
- The agent was verified on a small data set with one model. It cites stored ids and its answers are checked against the
  tool results; that is not a claim about general investigation quality.
- No physical hardware, no customer data, no safety certification.

## After the demo

Stop the stack (`touch var/demo/stop`; end the Gazebo host if it started), and **rotate the aicredits key**.
