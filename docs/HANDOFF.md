# Engineering handoff

For the engineer taking this repository over. Read with `CLAUDE.md` (working rules and invariants), `ARCHITECTURE.md`,
`DESIGN.md` (the interface contract) and `harness/` (features with evidence, decisions D-001 onward, progress, blockers).

## What the product is

One platform for robotics and laboratory teams, built on the OpenMHS engine (the verifier and the statistics):

| Capability | Where | Verified by |
|---|---|---|
| Release Intelligence: baseline vs candidate from recorded evidence | `services/api/app/{evaluations,releases,ingestion,evidence}`, `/releases` | engine-backed pytest, e2e |
| Hardware Hub: environments, discovery, read-only observation (WoT/LabThings, ROS 2 observer) | `app/hardware`, `packages/device-sdk`, `runtimes/{virtual-lab,ros-observer}` | pytest, e2e |
| Workflows: ordered device actions with a verification contract, durable worker, simulated-only commands | `app/workflows`, `/workflows`, `/workbench`, composer | pytest (real virtual lab), e2e |
| Experiments: immutable specs, approval of an exact checksum, trials on simulation hosts, capture, release verdicts | `app/experiments`, `runtimes/sim-host`, `/experiments` | pytest (real host), e2e, real Gazebo run |
| Digital twin: model registry, MCAP playback, events, baseline vs candidate ghost, explanations | `app/twin`, `/twin` | pytest, e2e |
| Agent tools (MCP, read-only plus request/propose) and the Strands agent harness | `packages/agent-tools`, `packages/agent-harness` | pytest (scripted model; no real-model claim) |

## Invariants you must keep

- Commands go only to environments the operator configured `simulated` whose devices report `simulated=true` (D-026).
  Physical environments are discover/read only.
- Every verdict is the engine's; the platform computes no statistic. A violated trial is not a release regression.
- Nothing is fabricated: missing evidence is unknown, simulated evidence is labelled, captures are checked against
  digests, an experiment approval applies to one checksum (D-037), hosts refuse rather than degrade (D-038).
- Uploads and captures stream in bounded memory (`app/twin/ingest.py`).

## Run, test, gate

```bash
uv sync --all-packages && npm --prefix apps/web ci
bash scripts/verify.sh                     # every gate: ruff, mypy (incl. sim-host, agent harness), Semgrep, contracts,
                                           # pytest with the real engine, web typecheck/lint/unit/build, audits
bash scripts/smoke.sh --e2e                # a fresh local stack (no Docker) and every Playwright suite
uv run python scripts/dev_stack.py --sim-port 8867 [--sim-catalog runtimes/sim-host/catalogs/gazebo-openamr.json]
PAP_REQUIRE_GAZEBO=1 uv run pytest services/api/tests/test_experiments_gazebo.py   # real Gazebo, opt-in
```

CI (`.github/workflows/ci.yml`) runs the gate with the browser suites, the trial dry run, secret/code/dependency scans
and the Docker Compose stack with an image scan on every push.

## How to extend

- **A new simulator** (MuJoCo, Isaac Sim): write a catalog for `runtimes/sim-host` whose scenario commands run the
  simulator and write `result.json` (measurements, artifacts, identity). Nothing in the platform changes
  (`docs/simulation-studio.md`, `pap.simulation-host/1`).
- **A new instrument**: expose it as a W3C WoT Thing (LabThings is the reference) with `simulated` declared; discovery
  records its properties and actions, and the composer offers them.
- **A new agent tool**: add a typed tool to `packages/agent-tools/src/pap_agent_tools/tools.py` (read-only, or a write
  that only records a request); the allowlist test pins the set on purpose.
- **A migration**: add `services/api/migrations/versions/00NN_*.py`; `test_scaffold.py` checks it matches the models.

## Where things stand (2026-11-23)

- 53 features verified in `harness/features.json`. HAR-001 (agent harness) awaits a real model run.
- Real Gazebo runs need the shared WSL workspace `~/p79` idle and clean; the host refuses otherwise.
- Open items and limits: `harness/blockers.md`, each feature's `limitations`, and the "Not built yet" sections of
  `docs/simulation-studio.md` and `docs/agent-harness.md`.
