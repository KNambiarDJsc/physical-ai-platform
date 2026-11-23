# Real evidence from the rehearsed journey

Every file here was produced by `scripts/journey_rehearse.py` against a running stack (API, durable worker, the LabThings
virtual laboratory, the pinned OpenMHS engine, and the real model through the Agent backend). Nothing was edited by hand
and no measurement was changed. The bench is **simulated**; each report says so on its first line.

| File | What it is |
|---|---|
| `dispense-50ul.workflow.json`, `dispense-50ul-blocked-line.workflow.json` | The two procedures exactly as stored: 50 µL, ±2 % tolerance, the contract, and (for the second) the injected and cleared simulated fault as visible steps. Their digests identify the procedure. |
| `success-run.report.html` / `.json` | The run on the normal bench: the pump reports 50 µL, the balance reads about 0.0498 g inside the 0.0489 to 0.0509 g window, the engine says SATISFIED (Supported success). |
| `failing-run.report.html` / `.json` | The run on the bench with a simulated partial blockage: the pump still reports success, the balance reads about 0.031 g, the engine says VIOLATED (a contradiction). The fault is a journaled step (`simulation.set_fault`), cleared by the last step. |
| `rehearsal.json` | The record of every rehearsal step (pass or fail), the engine build, the agent's answer, citations, drafted follow-up, token counts and cost, and the refusal session. It contains no key. |

A report is built only from stored records and has no generation time: regenerate it from the same run
(`GET /api/v1/orgs/<org>/workflow-runs/<run>/report.json`) and the bytes are identical. The rehearsal checks this.

Reproduce on a fresh workspace:

```bash
bash scripts/demo_up.sh
uv run python scripts/journey_rehearse.py --org lab-journey-r1 --out docs/demo/evidence   # add --no-agent to spend nothing
```

Run ids, timestamps and the last digits of the measurements differ between rehearsals (the bench has a seeded noise
model); the verdicts, the outcome classes and the structure do not.
