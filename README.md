# Physical AI Reliability Platform

Release Intelligence for robotics teams: did the candidate release make the robot better or worse, what does
independent evidence say about what actually happened, and is there enough evidence to decide?

Built on [OpenMHS](https://github.com/KNambiarDJsc/Open-MHS), the open-source Rust engine that verifies
physical outcomes (SATISFIED / VIOLATED / UNKNOWN) and compares releases with stated statistical rules. This
repository is the commercial application around it: workspaces, evidence management, evaluation jobs,
comparisons, drill-down and reports. It observes recorded evidence; it never controls robots.

**Status: early build.** See `harness/progress.md` for what works today, with test evidence, and
`harness/features.json` for every feature and its verification state.

## Layout

| Path | What |
|---|---|
| `packages/openmhs-bridge` | Runs the pinned OpenMHS binary; typed results with provenance |
| `services/api` | FastAPI service and evaluation worker |
| `apps/web` | Next.js application (not started) |
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

Docker Compose for the whole stack is planned (INF-003) and not available yet.

## Principles

Unknown outcomes are shown, not hidden. Reported and verified outcomes stay separate. Missing metadata is
marked unavailable, never invented. Every number carries the engine version, mapping revision and input
checksums that produced it. Synthetic or simulated evidence is labelled as such.
