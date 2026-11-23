# Session handoff (2026-11-23)

The state at the end of a very long session. All 54 features in `harness/features.json` are verified; what remains is
confirmation on the final tree, publishing, a UI review of the older pages, and a short list of unbuilt items. Read
`AGENTS.md` first, then this file. The full prompt for a new session is `NEXT_CLAUDE_PROMPT.md` beside it.

## Where the repository stands

- Branch `main`, working tree clean, HEAD `3d912c1`. `origin/main` is at `314f5a6` (CI green on all four jobs).
- **Nine local commits are not pushed** (the owner approves every push): `495f101`, `ed5ba97` (agent harness),
  `7f6ad91` (3D baseline-vs-candidate, workflow composer, members, onboarding docs), `bf941b4`, `61a6331` (handoff,
  code graph), `cf01ed8` (another session: onboarding verified, registry reconciled), `2e15ee8` (demo tooling),
  `737a27c`, `3d912c1` (harness verified with a real model).
- **Another agent session also commits to this repository** (`cf01ed8` appeared mid-session). Always read
  `git status` and `git log` first, never revert what you did not write, and keep commits small.
- A demonstration stack may still be running (web :3000, API :8000, from `bash scripts/demo_up.sh`, state `var/demo`).
  Stop it with `touch var/demo/stop` when done; its data is disposable.

## What was built and verified this session (evidence is in `harness/features.json`)

| Area | What | Key evidence |
|---|---|---|
| SIM-001..007 | simulation host contract, immutable experiment specs, approval of an exact checksum, execution through the durable worker, artifact capture and twin recordings, Experiment Studio, real Gazebo #79 run through the platform, release verdicts | real host and engine tests; browser journeys; Gazebo pre-fix 1.003 m VIOLATED, fix 0.080 m SATISFIED |
| TWN-006 | baseline vs candidate as a ghost in the 3D twin | vitest on real tracks; e2e |
| WF-002 | workflow composer across discovered instruments | e2e on the real virtual lab |
| ONB-001 | members in Settings, onboarding, deployment, handoff docs | e2e (verified by the other session) |
| HAR-001 | Strands agent harness: providers as config, fast paths, scoped discovery, parallel reads, bounded loops, approval per write, per-session and per-experiment budgets, traces, grounding | 17 tests with a scripted model **and** a real-model run (gpt-oss-120b, $0.0032) |
| Fixes | 96 MB upload `MemoryError` (read(limit+1) reserved the limit; now chunked), SIM-001 hang (undrained stderr pipe), racy CI test, three harness defects found by the real run | regression tests |

Last full gate on a recent tree: `bash scripts/verify.sh` **all passed** (pytest 301 passed, 5 skipped; harness 14 at that
time; web unit 57; Semgrep, mypy for every project, contracts, audit). `smoke.sh --e2e` last ran in full at 47 passed /
13 skipped, before TWN-006, WF-002 and the Studio additions; those specs passed individually (19 together) but the full
browser suite has not been re-run on the final tree.

## What is left, in order

1. **Confirm the final tree.** `git add -N . && NODE_OPTIONS=--max-old-space-size=2048 bash scripts/verify.sh` (about
   10 minutes; run it as a background command), then `bash scripts/smoke.sh --e2e`. Fix any failure at its cause.
2. **Publish, with the owner's approval for that push.** Push, then watch CI (`gh run watch`). New in CI since the last
   green run: `verify.sh` now also type-checks and tests `packages/agent-harness` (needs Strands from PyPI), the
   sim-host project, and `.github/workflows/ci.yml` has not been edited for them. If a job fails on those, fix the
   workflow, not the tests.
3. **Review the older pages visually** (Overview, Releases, Verification, Incidents, Evidence, Fleet, Integrations,
   Hardware, Workbench, Get started): screenshots in both themes at 1280x800, then fix what reads poorly. Standard: plain
   words before identifiers, every state (loading, empty, error with a recovery action), axe clean in both themes,
   `DESIGN.md` (section 6c is the approach used on the Studio). Add each changed page to `e2e/a11y.spec.ts`.
4. **Refresh the code graph** (`graphify update .`, then copy `graphify-out/GRAPH_REPORT.md` and `graph.json` to
   `docs/handoff/graphify/`; it was built at `bf941b4`).
5. **Owner actions** (not yours): rotate the aicredits key that was pasted in chat; approve pushes; decide whether the
   deployment guide should be tried on a real host.
6. **Not built yet** (each has a "Not built yet" note in its doc): MuJoCo and Isaac simulation hosts (same
   `pap.simulation-host/1` contract, no platform change); cancelling a running scenario; streaming artifacts to
   clients (served artifacts are bounded by the 96 MiB capture limit); agent traces stored in and shown by the platform
   (an Agents page); agent plans that resume after an approval; branching workflows; a split 3D view for two
   recordings beyond the ghost.

## Known limits to state, never hide

- The self-test simulation host is a kinematic model, not a simulator. Only the Gazebo runs are real simulation.
- The pre-fix Gazebo arm is the fix commit with two wiring files restored from `origin/main` for the run (recorded in the
  run identity), not a separate clean build of the pre-fix commit. The fix arm ran branch head `d6f810f`.
- One run per arm gives individual contract verdicts only; the engine's release comparison says insufficient evidence
  until it has enough known outcomes (it needs 30 per arm by default). Never present a violated trial as a regression.
- The agent harness was verified with one model on a small data set. It shows safe, grounded behaviour there, not
  general investigation quality. The model once credited the engine's 30-attempt rule to "the contract".
- No customer data and no physical hardware validation exist (`harness/blockers.md`).

## Pitfalls learned this session

- RAM is scarce (often 1 to 3 GB free of 16). Never start Docker locally. Build the web app with
  `NODE_OPTIONS=--max-old-space-size=2048`. Run long commands as ONE background command and read only summary lines;
  every wake-up re-sends the whole conversation.
- Real Gazebo uses the WSL distro `openmhs-ros`, workspace `~/p79`, shared with another project. The host refuses when
  Gazebo is running or the checkout is dirty. Real Gazebo tests are opt-in (`PAP_REQUIRE_GAZEBO=1`).
- PyPI is slow: `UV_HTTP_TIMEOUT=300 UV_CONCURRENT_DOWNLOADS=2`.
- `packages/agent-harness` and `runtimes/*` are separate uv projects: `uv run --project <dir> ...`.
- The tool transport can turn backslash escapes into raw characters inside files and can break very long shell
  heredocs: write files with the file tools, build special characters with `chr()` or code points.
- `str.translate` needs integer code points as keys, not characters.
- Leaked processes after test runs (virtual-lab and sim-host servers, a demo PostgreSQL) can block a fresh stack:
  list them by command line (`physical-ai-platform`) and stop only those.
- Another reason for slow progress is context size: start a new session per milestone rather than extending one.

## Secrets

Never write an API key to a file, log, trace, memory or commit. The harness reads `PAP_LLM_API_KEY`, `PAP_LLM_BASE_URL`,
`PAP_LLM_MODEL` from the environment (aicredits.in is OpenAI-compatible at `https://api.aicredits.in/v1`; the public
model list with prices is at `/v1/models`; `openai/gpt-oss-120b` is $0.037 in / $0.17 out per million tokens). Spend
needs the owner's explicit authorization each time, with a cap (`--max-usd`, `--experiment-max-usd`).
