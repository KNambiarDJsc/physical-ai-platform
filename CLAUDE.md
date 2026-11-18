# Physical AI Reliability Platform: instructions for coding sessions

Commercial, vendor-neutral release and outcome-verification platform for robotics teams, built on the
OpenMHS Rust engine. Read PRODUCT.md for why, ARCHITECTURE.md for how. The repository, not the
conversation, holds the state of the work.

## Start of every session

1. Read this file, `harness/progress.md` (top section), `harness/blockers.md`.
2. `git status` and `git log --oneline -10`.
3. `python scripts/check_features.py` — shows the registry state and the eligible next features.
4. `bash scripts/verify.sh --quick` to confirm the baseline before changing anything. If it fails, fixing
   the baseline is the task.
5. Pick ONE eligible feature (lowest priority number, dependencies verified). Work only on it.

## End of every session (or context window)

1. Run the feature's tests, then `bash scripts/verify.sh`.
2. Update the feature in `harness/features.json` only from evidence: paste the commands that passed into
   `verification.evidence`. Never mark `verified` because code exists.
3. Append to `harness/progress.md` (what changed, test evidence, next step); decisions to
   `harness/decisions.md`; anything blocking to `harness/blockers.md`.
4. Make a local commit as the checkpoint for the feature. Never push, tag or open PRs without explicit
   approval for that action.

## Invariants (do not break, do not work around)

- **Observation only.** Nothing in this repo sends commands to robots, PLCs or equipment, or sits in a
  robot's real-time path.
- **OpenMHS is the evaluation engine.** Verdicts come from `openmhs outcome verify`; statistics from
  `openmhs ops compare`. Never reimplement them in Python or TypeScript, never compute a new statistic
  in the API or the frontend. A missing capability goes into `docs/engine-contract-gaps.md`.
- **The engine is pinned** (`engine.lock.json`); the bridge checks the binary's SHA-256 before every run.
  Invoke it with an argument list, never a shell string.
- **Do not modify sibling repositories** (OpenMHS at `C:\Users\HP\Open-MHS` / `D:\openmhs-di`,
  OpenAMRobot AI Studio at `D:\openamrobot-ai-studio`). Read them; build from them with
  `scripts/build-openmhs.sh`, which exports the pinned commit and leaves the clone untouched.
- **Honest outcomes.** Missing evidence is never success. Reported and verified outcomes stay separate.
  Unknown is a result, shown, not hidden. Missing metadata is marked unavailable, never invented.
- **Tenant isolation.** Every project-scoped query goes through the caller's organization. A foreign id
  returns 404.
- **No fake data presented as real.** Synthetic or simulated evidence is labelled as such everywhere it appears.
- **Mocks are not end-to-end evidence.** A mocked engine may test an interface, never a criterion that
  names the real engine.

## Commands

| What | Command |
|---|---|
| Registry check / next feature | `python scripts/check_features.py` |
| Fast gate (registry, lint, unit) | `bash scripts/verify.sh --quick` |
| Full gate | `bash scripts/verify.sh` |
| Build pinned engine | `OPENMHS_SRC_REPO=C:/Users/HP/Open-MHS bash scripts/build-openmhs.sh` |
| Python tests | `uv run pytest` (from repo root) |
| Local stack (no Docker) | `uv run python scripts/dev_stack.py` (web must be built first) |
| Smoke + browser e2e | `bash scripts/smoke.sh --e2e` (needs a built engine; starts and stops its own stack) |
| Same on Docker Compose | `bash scripts/smoke.sh --compose --e2e` (needs a running Docker engine) |
| Browser sign-in through OIDC | `bash scripts/smoke.sh --oidc` (local oidc-provider + API in OIDC mode) |
| Semgrep (project rules) | `uvx --from semgrep==1.183.0 semgrep scan --config .semgrep/rules.yml --error --metrics=off` and `uvx --from semgrep==1.183.0 python scripts/check_semgrep_rules.py` |
| Bounded autonomous loop (opt-in) | `bash scripts/loop.sh --iterations 1` |

Engine for tests: `OPENMHS_BIN` and `OPENMHS_BIN_SHA256` (written to `.engine/build.json` by the build
script). Database for tests: `PAP_TEST_DATABASE_URL`; when unset, tests start a throwaway PostgreSQL with
`pgserver` (dev dependency). Never point tests at SQLite: the product runs on PostgreSQL.

## Machine constraints (this workstation)

- C: is nearly full. Keep caches, engine builds and temp files on D: (`TMP=D:/openmhs-tmp/tmp`).
- RAM is scarce; build Rust with `-j 2`; do not start Docker Desktop without asking the user.

## Writing

Commits, docs and PR text are written in the user's voice. No AI tool names, no "Generated with" footers,
no co-author trailers. Keep prose plain and specific; numbers carry their basis (n, interval, evidence class).

## Graphify (optional)

A local code graph may exist in `graphify-out/` (gitignored, built with `graphify update .`, AST only, no LLM).
When it exists, `graphify query "<question>"`, `graphify path "A" "B"` and `graphify explain "X"` are a quick
first look for codebase questions; read the source before relying on an answer. Nothing depends on it: no gate,
hook or script requires Graphify. `.graphifyignore` keeps evidence data, results and credentials out of it.
Personal hooks that nudge towards the graph live in `.claude/settings.local.json` (not committed).
