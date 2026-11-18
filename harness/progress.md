# Progress

Newest entry first. Each entry: what changed, evidence, current state, next step, anything uncommitted.

## 2026-11-18 — Session 1 (later): web application and the first browser-verified end-to-end flow

**State now:** 16 of 23 features verified (adds WEB-001, RI-005, RI-006, RI-007). Open: SEC-001 (containers,
CI scanners), RI-008 (reports), INF-003 (Compose, needs Docker), E2E-001 (failure-path e2e + clean install),
AUTH-002 (browser OIDC), OBS-001; DATA-004 blocked on Docker.

**Evidence:** `bash scripts/verify.sh` full gate green (132 Python tests, audit 11/11, 8 web unit tests, build).
Playwright flow (`apps/web/e2e/release-flow.spec.ts`, run against `uv run python scripts/dev_stack.py`) passed in
Chromium: releases -> upload -> mapping -> evaluation -> comparison -> episode drill-down, on the real worker and
pinned engine. It is not in verify.sh because it needs the running stack.

**Findings from looking at the screenshots:** columns hidden by horizontal scroll at 1280 px, collapsed
interval plot, overflowing digests, and unnamed form selects (a11y). All fixed.

**Next:** RI-008 reports (deterministic JSON, HTML rendered from it) -> E2E-001 failure paths (invalid
artifact, unauthorized, duplicate, worker restart through the UI, incompatible releases) + smoke.sh ->
SEC-001 -> INF-003 when Docker is available. Dark theme not yet reviewed visually.

**Gotchas:** stopping dev_stack on Windows: kill by PID tree (`taskkill /T /F`); a PowerShell filter on the
command line also matches itself. Python heredocs mangle `
` in string literals; use the Edit tool.

## 2026-11-18 — Session 1 (continued): the first real Release Intelligence workflow runs end to end in the API

**State now:** 12 of 22 features verified: INF-001, INF-002, CORE-001, CORE-002, DATA-001, DATA-002, DATA-003,
AUTH-001, RI-001, RI-002, RI-003, RI-004. In progress: RI-005 (TS client missing), SEC-001 (containers, CI
scanners). Blocked: DATA-004 (S3 adapter, needs Docker). Not started: WEB-001, RI-006/007/008, INF-003,
E2E-001, OBS-001.

**What works (all against PostgreSQL and the pinned engine, 132 tests, `bash scripts/verify.sh` green):**
- API: orgs, members, service credentials, audit log, projects, releases (engine-identical manifest digests),
  artifact upload (content-addressed, limited, sniffed), immutable mapping revisions, evaluations (submit,
  list, get, cancel, comparison, validation, incidents, episodes with filters, episode detail).
- Worker (`python -m app.workers.run`): SKIP LOCKED claim with lease + heartbeat, cancellation kills the
  engine, timeout, bounded retry of transient errors, recovery of a hard-killed worker's job, lease-guarded
  persistence. Results stored verbatim with sha256; events file and engine store kept as artifacts; a re-run
  of the engine on the stored events reproduces the stored comparison byte for byte.
- Demo (synthetic, labelled): reported comparison says **improvement**, verified says **insufficient
  evidence**; contradictions 7 -> 25. `uv run python scripts/run_demo_pipeline.py` prints it without the DB.
- Isolation test covers every org-scoped route twice (victim path; attacker path with victim ids). It found a
  real 500 on long denied URLs (fixed, D-011).

**Next (in order):** WEB-001 web scaffold + generated TS client (closes RI-005) -> RI-006 comparison UI ->
RI-007 episode drill-down -> RI-008 reports -> E2E-001 Playwright flow. INF-003 / SEC-001 containers need
Docker (B-001) or CI.

**Gotchas:** FastAPI 0.163 includes routers lazily (`app.routes` does not list them; enumerate the OpenAPI
document). Starlette warns that httpx TestClient support is deprecated (harmless for now). The worker's
`PAP_WORKER_LEASE_S` minimum is 5 s; tests use 5.

## 2026-11-18 — Session 1: harness, engine audit, pinned bridge

**State now**
- Verified: CORE-001 (engine audit), CORE-002 (pinned bridge). In progress: INF-001 (harness; loop.sh dry run
  pending its clean-tree check). Everything else unstarted.
- Pinned engine: OpenMHS `e9ef873` (origin/main today), release build `sha256:d51af06f…` at
  `.engine/bin/openmhs.exe` (gitignored; rebuild with `scripts/build-openmhs.sh`, 9 min with `-j 2`).

**Done, with evidence**
- `python scripts/audit_openmhs.py` → 11/11 against the pinned binary: 469-record/124-verdict fixture
  confirmed; Gazebo A/B verified comparison 15/30 → 0/30 failed attempts, Newcombe −0.5 (−0.763, −0.117),
  verdict `insufficient_evidence` (10 scenarios per arm); reported comparison shows 0 failures in both arms
  on the same data; 9 incidents with timelines on the real CoreSense flights; paired McNemar p = 0.508 on
  PushT (simulation); RFC 0004 corpus 27/27 verdicts and exit codes as expected.
- `packages/openmhs-bridge`: digest-checked, shell-free runner with timeout/cancel/output cap; typed models
  for verify/ingest/compare/incidents/show; `Result` carries raw output + provenance (version, digest,
  commit, interfaces). 31 tests pass with `PAP_REQUIRE_ENGINE=1`.
- Findings that shape the pipeline: (1) an unknown release label is NOT an engine error (exit 0, empty arm,
  warning), so the bridge checks `expect_a/expect_b` manifest digests; (2) ingest exits 3 on any rejection;
  (3) values are passed as `--opt=value` so a label can never become a flag (tested with hostile labels).
- Harness: CLAUDE.md, AGENTS.md, PRODUCT.md, ARCHITECTURE.md, README, feature registry (20 features) +
  checker, decisions D-001..D-008, blockers B-001..B-004, integration registry, `.claude/` (settings with
  reviewed hooks, five agents, engineering-loop skill), `scripts/verify.sh` (full gate passes),
  `scripts/loop.sh` (opt-in, bounded), local secret scan.
- `bash scripts/verify.sh` → all gates passed (API and web gates report "not present yet").

**Next**
1. INF-001: dry-run `PAP_LOOP=1 scripts/loop.sh --dry-run` on a clean tree, then mark verified.
2. INF-002 (API scaffold on PostgreSQL via pgserver, Alembic round trip, /healthz with engine status).
3. DATA-001 contracts, AUTH-001, then DATA-002/003, RI-001/002 toward RI-003 (first real job).

**Environment notes**
- Docker engine is off and RAM is scarce (B-001): PostgreSQL for tests comes from `pgserver` (Python 3.12).
- `UV_CACHE_DIR=D:/uv-cache`; C: has under 4 GB free.
- Gotcha: writing `"\x00"` through a bash heredoc into Python source produced a literal NUL byte; use `chr(0)`
  or the file tools.
