# Handoff to Codex: Physical AI Platform (2026-11-23)

You are taking over an active repository. Read in this order, then start on the open work below:

1. `AGENTS.md`: the rules every agent follows here (scope, evidence, safety, commits).
2. `docs/HANDOFF.md`: what exists, where, the invariants, how to run, test and extend.
3. `docs/handoff/graphify/GRAPH_REPORT.md`: the code map (hubs, communities); `graph.json` beside it for queries.
4. `harness/features.json` (54 features, each with acceptance criteria and recorded evidence), `harness/decisions.md`
   (D-001 to D-039), the newest entries of `harness/progress.md`.

## Using the code graph

```bash
graphify query "how does an experiment approval reach the worker"   # BFS over graph.json
graphify explain "execute_run"                                         # a node and its neighbours
graphify path "approve" "execute_run"                                  # shortest path between two symbols
graphify affected "WorkflowDef"                                        # what depends on it
graphify update .                                                      # refresh after code changes (AST only, free)
```

`--graph docs/handoff/graphify/graph.json` uses the committed snapshot; without it, graphify reads `graphify-out/`
(gitignored, rebuilt by `graphify update .`). The graph was extracted from code only, with no language model, and
contains no evidence files, keys or machine paths. It is a map: read the source before relying on an answer.

## State

- `origin/main` is at `314f5a6` (CI green on all four jobs, including the Docker Compose stack). Local commits after it
  (not pushed; the user approves every push): agent harness (HAR-001), its orchestration, the 3D baseline-vs-candidate
  comparison (TWN-006), the workflow composer (WF-002), members and onboarding docs (ONB-002), and this handoff.
- 53 features verified, with HAR-001 awaiting a real model. Customer onboarding is tracked as ONB-002.
  The quick gate and local browser smoke passed on 2026-11-23 (301 pytest and 51 browser tests passed).

## Open work, in order

1. Review the current local checkpoint before asking for approval to push.
2. Review the status of the full gate in `harness/progress.md`.

3. **HAR-001 real-model run**: needs the user's key as environment variables (`PAP_LLM_API_KEY`, `PAP_LLM_BASE_URL`,
   `PAP_LLM_MODEL`) and explicit spending authorization. Never write the key anywhere. Use a cap
   (`--max-usd 0.20`), record the trace path, the answer's grounding and the usage; claim only what that run shows.
4. **UI and UX pass over every page** (`DESIGN.md`, section 6c for the Studio's approach): plain words before
   identifiers, every state (loading, empty, error with a recovery action), axe in both themes, screenshots reviewed.
   The Studio, twin comparison, composer and members were done this way; the older pages were not reviewed again.
5. **Not built yet** (see each doc's "Not built yet"): MuJoCo and Isaac simulation hosts (same contract, no platform
   change), cancellation of a running scenario, streaming artifacts to clients, traces stored in the platform (an
   Agents page), multi-step agent plans that resume after an approval, branching workflows.

## Rules you must keep

- Commands only to operator-configured simulated environments whose devices report `simulated=true` (D-026).
- Verdicts and statistics are the OpenMHS engine's; a violated trial is not a release regression.
- Never fabricate telemetry, measurements or outcomes; never weaken or delete a test to pass a gate.
- Commits are local, in the user's voice, with no AI attribution, co-author trailer or "generated with" line; use
  `git commit -F <file>`. Never push without the user's explicit approval for that push.
- No paid service or paid inference without explicit authorization. Never store API keys.
- Do not modify upstream repositories (OpenMHS, OpenAMRobot); the engine is pinned (`engine.lock.json`).

## Pitfalls on this machine

- Memory is scarce (often 1 to 3 GB free of 16): never start Docker locally; build the web app with
  `NODE_OPTIONS=--max-old-space-size=2048`; run long suites as one command and read only the summary.
- Real Gazebo runs use the WSL distribution `openmhs-ros`, workspace `~/p79`, which another project also uses. The
  host refuses when Gazebo is already running or the checkout is dirty; do not stop or clean someone else's work.
  Real Gazebo tests are opt-in: `PAP_REQUIRE_GAZEBO=1 uv run pytest services/api/tests/test_experiments_gazebo.py`.
- PyPI is sometimes slow here: `UV_HTTP_TIMEOUT=300 UV_CONCURRENT_DOWNLOADS=2 uv sync`.
- `packages/agent-harness` and `runtimes/*` are separate uv projects (`uv run --project <dir> ...`).
- Browser suites need a running stack: `uv run python scripts/dev_stack.py --lab-port 8865 --sim-port 8868
  --ros-replay runtimes/ros-observer/tests/fixtures/openamr-upperbody-mock.snapshot.json` (each flag enables the
  specs that need it; others skip and say so).
