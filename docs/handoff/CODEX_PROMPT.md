# Prompt for Codex (paste this as the first message)

You are taking over the **Physical AI Platform** repository at `D:\physical-ai-platform` (Windows 11, Git Bash and
PowerShell, WSL2 distro `openmhs-ros`). A previous agent built most of it over many sessions; the owner (KNambiarDJsc)
is demonstrating it to stakeholders and wants it kept working, verified and honest. Work like a careful senior engineer
who inherits a production codebase: read first, change little, prove everything.

## 1. Read, in this order (do not skip, do not re-explore the repo afterwards)

1. `AGENTS.md`: the rules for every agent in this repository. They override your defaults.
2. `docs/HANDOFF.md`: what exists, where, the invariants, how to run, test and extend.
3. `docs/handoff/CODEX_HANDOFF.md`: current state, open work in order, pitfalls of this machine.
4. `docs/handoff/graphify/GRAPH_REPORT.md` and `graph.json`: a code map. Query it instead of grepping blindly:
   `graphify query "<question>" --graph docs/handoff/graphify/graph.json`, also `explain`, `path`, `affected`.
   It is a map; read the source before relying on an answer. Refresh with `graphify update .` (free, no key).
5. `harness/features.json` (every feature with acceptance criteria and recorded evidence), `harness/decisions.md`
   (D-001 to D-039), `harness/progress.md` (newest entries), `harness/blockers.md`, `DESIGN.md`.

## 2. What the product is

One platform for robotics and laboratory teams, built on the **OpenMHS** verification engine (a pinned Rust binary,
never modified): Release Intelligence (baseline vs candidate, with the engine's statistics), a Hardware Hub (instruments
and robots via W3C WoT/LabThings and a ROS 2 observer), durable workflows across instruments, **simulation experiments**
(immutable versions, approval of an exact checksum, trials on simulation hosts including real Gazebo, artifact capture,
engine verdicts, release verdicts), a **Digital twin** (3D replay, events, baseline-vs-candidate ghost, explanations),
permissioned agent tools (MCP) and a **Strands agent harness** (`packages/agent-harness`).

Stack: FastAPI + PostgreSQL + a durable worker (`services/api`), Next.js 15 (`apps/web`), uv-managed Python workspace,
separate uv projects under `runtimes/*` and `packages/agent-harness`, Playwright for browser tests, Docker Compose in CI.

## 3. Non-negotiable rules

- **Commands go only to simulated environments** the operator configured `simulated` whose devices also report
  `simulated=true` (D-026). Physical environments are discover/read only. Never send a command to hardware.
- **Verdicts and statistics are the engine's.** A violated trial is one run breaking its contract; it is NOT a release
  regression. Never compute a statistic in the platform or the UI.
- **Never fabricate** telemetry, measurements, outcomes or test results. Real runs only; say plainly what was skipped.
- **Never weaken, skip or delete a test** to make a gate pass; fix the cause. If the same failure happens twice, stop and
  diagnose; record unresolved failures in `harness/blockers.md`.
- **Git**: commits are local, in the owner's voice, with NO AI attribution, NO `Co-Authored-By`, NO "Generated with"
  line. Use `git commit -F <file>`. **Never push without the owner's explicit approval for that push.**
- **No paid services or paid inference** without explicit spending authorization. **Never store an API key** in a file,
  log, trace, memory, commit or prompt; keys come from environment variables only (`PAP_LLM_API_KEY`,
  `PAP_LLM_BASE_URL`, `PAP_LLM_MODEL`). Cap spend per run.
- **Do not modify upstream repositories** (OpenMHS, OpenAMRobot). The engine is pinned in `engine.lock.json`.
- Do not start Docker locally (RAM is scarce). Real Gazebo runs use the shared WSL workspace `~/p79`; the host refuses
  when Gazebo is already running or the checkout is dirty. Do not stop or clean another session's work there.
- Another agent session may be working in this repository at the same time. Check `git status` and `git log` before
  you start, do not revert changes you did not make, and keep your commits small and focused.

## 4. How to work (the harness loop)

For each piece of work: confirm or write the acceptance criteria in `harness/features.json` first; implement the
smallest coherent slice; run only the tests for that slice while iterating; run the full gate once per milestone; record
evidence (commands and results), limitations and decisions in `features.json`, `progress.md` and `decisions.md`; commit
locally. Run long suites as ONE blocking or background command and read only summary lines.

```bash
uv sync --all-packages && npm --prefix apps/web ci          # PyPI is slow here: UV_HTTP_TIMEOUT=300 UV_CONCURRENT_DOWNLOADS=2
git add -N . && NODE_OPTIONS=--max-old-space-size=2048 bash scripts/verify.sh   # the full gate (~10 min): lint, mypy, Semgrep, pytest with the real engine, web typecheck/lint/unit/build, audits
bash scripts/smoke.sh --e2e                                  # a fresh local stack (no Docker) and every Playwright suite
uv run python scripts/dev_stack.py --lab-port 8865 --sim-port 8868 --ros-replay runtimes/ros-observer/tests/fixtures/openamr-upperbody-mock.snapshot.json   # a stack to develop against
PAP_REQUIRE_GAZEBO=1 uv run pytest services/api/tests/test_experiments_gazebo.py   # real Gazebo, opt-in, ~1.5 GB, ~2 min per run
cd packages/agent-harness && uv run pytest                   # harness orchestration tests (scripted model)
```

## 5. Open work, in priority order

1. **Confirm the tree is green**: run the full gate and `smoke.sh --e2e`; fix any failure at its cause. Then ask the owner
   before pushing; CI (`.github/workflows/ci.yml`) must be green afterwards.
2. **HAR-001 real-model run** (the only feature not yet verified): needs the owner's environment variables and explicit
   spending authorization. Run e.g. `uv run pap-harness ask --org demo --as ada --max-usd 0.20 "<question about a real
   experiment run>"`, record the trace path, the grounding result and the usage; claim only what that run shows. The
   14 harness tests use a labelled scripted model and prove orchestration only, not model quality.
3. **UI and UX pass over the older pages** (Overview, Releases, Verification, Incidents, Evidence, Fleet, Integrations,
   Hardware, Workbench): plain words before identifiers, every state (loading, empty, error with a recovery action),
   axe in both themes, review real screenshots. `DESIGN.md` section 6c describes the approach used on the Studio.
4. **Not built yet**: MuJoCo and Isaac Sim hosts (same `pap.simulation-host/1` contract, no platform change),
   cancelling a running scenario, streaming artifacts, agent traces stored in and shown by the platform, agent plans that
   resume after an approval, branching workflows. Each has a "Not built yet" note in its doc.

## 6. Definition of done for anything you finish

Acceptance criteria written first; tests that exercise the real engine/worker/host (no mocks for end-to-end claims); the
full gate green; evidence, limitations and any decision recorded; a local commit in the owner's voice; the owner told
what was verified, what was skipped and why, and what is still not built.
