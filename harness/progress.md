# Progress

Newest entry first. Each entry: what changed, evidence, current state, next step, anything uncommitted.

## 2026-11-19 — Session 4: Milestone D, trial pack for an independent engineer

**State now:** 26 of 27 features verified (adds INF-003, SEC-001 on CI run 44393338284; EVAL-001; TRIAL-001). Open:
OBS-002 (collector and dashboards, unstarted; not needed for the trial).

**trial/**: one-command Docker install (`bash trial/start.sh`, no credentials of ours), a 6-task exercise with an
answer key, the same questions answered by a plain-Python script checked against the engine (14 cases), an
evaluation form, LIMITATIONS (G-7, G-8 first), a pilot brief, and our own dry run. Clean GitHub runner: install to
Ready in 512 s, exercise matched every answer, reset left nothing. The script answers in 0.03 s where the platform
needs 4-18 s: recorded as where the script is faster. First clean run failed on a SIGPIPE bug in start.sh (fixed).

**Not done, and not claimable:** no external engineer has tried it, so there is no feedback of any kind; the
pilot brief's contact line is blank; Docker Desktop on Windows/macOS is untested; the repo is private.

**Next:** hand the trial to a real engineer (owner grants repo access); then act on what they report. Milestone D's
competitive baseline stays open until an engineer has done both workflows.

## 2026-11-19 — Session 3: deployment validation on CI, first real robot evidence

**Pushed** to the private repo KNambiarDJsc/physical-ai-platform (user approved). CI findings, all real:
the worker ignored a cancellation or an exceeded time limit when a whole run fitted inside the first heartbeat
interval (fixed, D-022 note in the commit; deterministic tests); the Python/Node base images carried 46/23 fixable
HIGH/CRITICAL OS findings (D-023: newer digests, npm removed from the web runtime). The Compose job on a clean
runner built the images (engine compiled in the image), ran the stack, passed the non-root, worker-limit, engine
and proxy checks, the API smoke and 7/7 browser tests including a worker killed from the host. The security job
(gitleaks, Semgrep with rule self-test, Trivy fs) passed. Graphify installed in a narrower form (D-022).

**Milestone B (EVID-001, verified):** CoreSense real drone flights through the platform, see
examples/coresense/README.md. Robots reported every GoTo succeeded; motion capture shows about 9 in 10 claimed
arrivals outside the assumed 0.20 m at the claim (the drones arrive about 0.5 s later). Found and fixed: cancelled
goals counted as contradictions; added the `physical` evidence class.

**Milestone C (EVAL-001, verified):** MuJoCo reaching arm, pre-registered (0971184) before the held-out run;
engine: 50 ms latency regression detected (+97 pp), 20 ms regression detected (+21 pp; robot self-reports
overstated it 4.5-fold, 118 contradictions), no-change control gave no regression verdict. New engine gaps G-7
(only pass/fail rates compared; the 20 ms shift is a 3.6x loss of accuracy) and G-8 (no change cannot be
established with a near-perfect baseline). More CI-found defects fixed: OIDC step hit a stale web server (process
groups + port guard), and the port guard itself counted TIME_WAIT as busy on Linux.

**Next:** INF-003 and SEC-001 to verified once a fully green CI run is recorded; Milestone D (competitive
baseline: an engineer doing the same analysis with a script) and unfamiliar real-world evidence.

## 2026-11-18 — Session 2: reports, failure-path e2e and the smoke script

**State now:** 18 of 23 features verified (adds RI-008, E2E-001). Open: SEC-001 (containers, worker limits, CI
scanners), INF-003 (Compose; needs a Docker engine, B-001), AUTH-002 (browser OIDC), OBS-001 (after INF-003);
DATA-004 blocked on Docker.

**Evidence:** `bash scripts/verify.sh` full gate green (136 Python tests with the engine required, audit
11/11, 8 web unit tests, web build). `bash scripts/smoke.sh --e2e` exit 0: API smoke on a fresh stack plus 7/7
Playwright tests (happy path entirely in the UI incl. creating the organization and project and exporting
both reports; failure paths: non-text upload, rejected artifact, same release, absent task type, too few
known outcomes, worker hard-killed mid-job -> attempt 2 of 3, duplicate submission, outsider).

**Changes:** `services/api/app/evaluations/reports.py` (pap.report/1 JSON + HTML from it), `report.json` /
`report.html` routes (audited, CSP on the HTML), download buttons on the comparison page, organization and
project creation in the overview, minimum-known-units input, runtime API proxy route (D-013), supervised
worker + stop file + state dir in dev_stack (D-015), `scripts/smoke.sh`, `scripts/smoke_api.py`,
`apps/web/e2e/failure-paths.spec.ts`. The `demo` fixture moved to conftest.py.

**Findings:** the next.config rewrite pinned the API address at build time (D-013). The outsider sees
"organization not found" (the API does not even confirm the organization exists); my test had expected
"evaluation not found".

**Later the same session (SEC-001 / INF-003, both still in progress):** Dockerfiles (non-root, engine built
from engine.lock.json inside the image), docker-compose.yml (read-only services, worker CPU/memory/pids limits,
healthchecks; `docker compose config` validates), `scripts/smoke.sh --compose` (non-root, limits, engine,
proxy, API smoke, e2e), `.github/workflows/ci.yml` (gate + e2e, gitleaks/Semgrep/Trivy as digest-pinned
images, Compose job with image scans). Ran the scanners locally at the CI versions: gitleaks history clean;
Semgrep project rules clean and self-tested; Trivy found postcss 8.4.31 inside next (2 HIGH) -> npm override
(D-017) -> clean. Web standalone server checked locally with a run-time API address.

**Then AUTH-002 (verified):** browser sign-in through OIDC (D-019): `src/lib/server/auth.ts`, `/auth/login`,
`/auth/callback`, `/auth/logout`, `/auth/session`, the proxy attaching the session's token. `bash scripts/smoke.sh
--oidc` runs a real oidc-provider instance + the API in OIDC mode; 3/3 browser tests (PKCE flow, cookie flags,
no token readable by the page, forged header ignored, sign-out, forged cookie refused, no dev sign-in in OIDC
mode). Found and fixed: the API's issuer check was a string-prefix match (`http://localhost.evil.example`).

**Then OBS-001 (verified, split per D-020):** JSON logs with request/job/trace ids and redaction, Prometheus
metrics (job states from the DB, request/job/engine durations, engine failures), one OTel trace from the API
request through the worker's job span to every engine process (context stored with the job). Bridge observer
hook for engine telemetry. FastAPI's own telemetry switched off (it recorded concrete URLs). The isolation
guard caught /metrics hidden from the schema; it is in the schema now.

**Then DATA-004 (verified, D-021):** S3Storage behind the same interface, tested against a real SeaweedFS
4.52 server run natively (no Docker): shared contract test on both adapters, tamper and size-limit checks, and a
full evaluation with S3 as the artifact and bundle store. `scripts/get-seaweedfs.sh` fetches the pinned release
for CI. Locally the permission check refused running that script (it downloads and executes a binary), so the
tests used the binary I had fetched and checksum-checked by hand into D:/tools (PAP_WEED_BIN); the user approved
using it and recording DATA-004 as verified on that basis.

**State now:** 21 of 24 verified. In progress: INF-003, SEC-001 (both wait only for containers to run).
Unstarted: OBS-002 (needs INF-003). Nothing is blocked except on Docker or a push.

**Next:** run `bash scripts/smoke.sh --compose --e2e` when Docker can be started (or CI after an approved
push) to verify INF-003 and finish SEC-001 -> OBS-002.

**Gotchas:** (1) Next 15.5 on this machine left the evaluation page out of its own client reference manifest
("Could not find the module ... in the React Client Manifest", 500) whenever the page imported a NEW
component file (`ReportActions.tsx`, with or without "use client"); defining the component in the page file
fixed it. Check `page_client-reference-manifest.js` for the page's own `page.tsx` if a page 500s after build.
(2) C: filled to 0 bytes mid-run (Remote Desktop traces again, 16 GB, deleted under the standing rule); the
smoke script now keeps TMP/TEMP under var/smoke/tmp. (3) `taskkill /T` exits non-zero when part of the tree is
already gone; check the process instead of the exit code.

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
