# Physical AI Reliability Platform

One platform for robotics and laboratory teams to run, verify and decide: Release Intelligence (did the candidate
make the robot better or worse, and is there enough evidence to say), a Hardware Hub for instruments and robots, durable
workflows across instruments, simulation experiments with approval, a Digital twin to replay and compare runs, and
permissioned agent tools.

Built on [OpenMHS](https://github.com/KNambiarDJsc/Open-MHS), the open-source Rust engine that verifies physical
outcomes (SATISFIED / VIOLATED / UNKNOWN) and compares releases with stated statistical rules. Commands go only to
simulated environments; physical equipment is discovered and read, never commanded.

Start here: [docs/onboarding.md](docs/onboarding.md) (a team's first hour), [docs/deployment.md](docs/deployment.md)
(install and operate), [docs/HANDOFF.md](docs/HANDOFF.md) (for engineers). Features with their verification evidence:
`harness/features.json`.

## Layout

| Path | What |
|---|---|
| `packages/openmhs-bridge` | Runs the pinned OpenMHS binary; typed results with provenance |
| `services/api` | FastAPI service and evaluation worker |
| `apps/web` | Next.js application (Release Intelligence workspace, comparison, episodes, report export) |
| `runtimes/` | Virtual laboratory (LabThings), ROS 2 observer, simulation host (`pap.simulation-host/1`) |
| `packages/device-sdk`, `packages/agent-tools`, `packages/agent-harness` | Device adapters; typed agent tools (MCP); the Strands agent harness |
| `harness/` | Feature registry, progress, decisions, blockers, evaluation results |
| `docs/` | Capability audit, engine interface gaps, integration registry, decisions |
| `scripts/` | Build, verify, audit, loop, hooks |

## Getting started (development)

Requirements: Python 3.12 via `uv`, Rust toolchain (to build the engine), a local clone of OpenMHS.

```bash
uv sync --all-packages                                            # Python workspace
OPENMHS_SRC_REPO=/path/to/Open-MHS bash scripts/build-openmhs.sh  # pinned engine -> .engine/bin, .engine/build.json
python scripts/audit_openmhs.py                                   # needs OPENMHS_BIN; checks the engine itself
bash scripts/verify.sh                                            # every gate
```

Tests need PostgreSQL: set `PAP_TEST_DATABASE_URL`, or leave it unset to start a throwaway server with
`pgserver` (development dependency). Engine-backed tests skip when the engine is not built, and fail instead of
skipping with `PAP_REQUIRE_ENGINE=1` (the full gate sets it).

Run the whole platform locally without Docker (PostgreSQL via pgserver, API, worker, web; development
identity only):

```bash
npm --prefix apps/web ci && npm --prefix apps/web run build
uv run python scripts/dev_stack.py            # http://127.0.0.1:3000, API on :8000
bash scripts/smoke.sh                          # fresh stack in var/smoke, one real evaluation over HTTP
bash scripts/smoke.sh --e2e                    # plus the Playwright suites (happy path and failure paths)
```

Docker Compose for the whole stack: `docker compose up -d --build` (see docs/deployment.md); CI builds and tests it.

## Principles

Unknown outcomes are shown, not hidden. Reported and verified outcomes stay separate. Missing metadata is
marked unavailable, never invented. Every number carries the engine version, mapping revision and input
checksums that produced it. Synthetic or simulated evidence is labelled as such.
