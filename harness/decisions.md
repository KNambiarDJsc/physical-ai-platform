# Decisions

Newest last. Each entry: date, decision, why, what would change it. Longer records live in `docs/decisions/`.

## D-001 (2026-11-18) Repository on D:, separate from OpenMHS and AI Studio
`D:\physical-ai-platform`, own Git history. C: has under 4 GB free; node_modules, virtualenvs and engine
builds would not fit. Revisit if the user wants it elsewhere.

## D-002 (2026-11-18) Engine boundary = the OpenMHS CLI with `--json`, pinned by commit and binary SHA-256
OpenMHS exposes `ops` and `outcome` only through its CLI (no library API for Python, no HTTP route for
`ops`). Its own importers use the same boundary. Pinned commit `e9ef873` (origin/main on 2026-11-18).
The binary is built by `scripts/build-openmhs.sh` from a `git archive` of that commit, so the OpenMHS clone
is never modified. Would change if OpenMHS publishes a versioned library or service API (gap G-1).

## D-003 (2026-11-18) One engine store per evaluation job
Each job ingests its own events into a fresh `ops.sqlite`. Results are then a pure function of (inputs,
mapping, config, engine digest), which makes idempotency and reproduction exact. Cost: no cross-job queries
inside the engine; history lives in PostgreSQL. Would change when Fleet Intelligence needs cross-evaluation
correlation in the engine.

## D-004 (2026-11-18) Verdicts per episode via `openmhs outcome verify`, statistics via `ops compare`
The platform never computes a verdict or a statistic. The per-episode outcome class (supported success,
contradiction, ...) is a labelled cross-tabulation of the engine's reported value and verdict + reason
codes, defined in ARCHITECTURE.md, not a new method.

## D-005 (2026-11-18) Job queue: own table with SKIP LOCKED, not Procrastinate (for now)
The evaluation job is a domain entity the UI shows (state, error, provenance). Procrastinate would add a
second job table with its own states and schema managed outside Alembic. A lease-based claim on
`evaluation_jobs` is ~150 lines and fully tested. Revisit when we need periodic jobs, several queues or
priorities.

## D-006 (2026-11-18) Python 3.12 for the API; pgserver as a dev-only PostgreSQL
Docker Desktop is not running on this workstation and RAM is scarce, so tests need PostgreSQL without
Docker. `pgserver` (bundled PostgreSQL binaries, wheels up to cp312 on Windows) gives a real server.
CI and Compose use the official `postgres` image. SQLite is never used for platform tests.

## D-007 (2026-11-18) OIDC validation with PyJWT, not Authlib
The API is an OAuth resource server: it only validates bearer JWTs against a JWKS. PyJWT (`PyJWKClient`)
covers that with a smaller surface. Authlib becomes relevant if the API itself runs login flows (it does
not; the web app or an IdP such as Keycloak does).

## D-008 (2026-11-18) Copy of `conditions_of` from OpenMHS, with a parity test
`outcome.verified.conditions` must be built from the verifier report exactly as OpenMHS's importer does
(`python/openmhs/importers/coresense_verify.py::conditions_of`, Apache-2.0). It is not a public API, and
importing a CoreSense-specific module would couple us to an internal. The bridge carries a 15-line copy
with attribution; a test compares it to the original when the OpenMHS checkout is present; the engine
itself refuses conditions that contradict the verdict. Gap G-2 asks OpenMHS to publish it.

## D-009 (2026-11-18) Split the web scaffold out of INF-002 into WEB-001
INF-002 mixed the API and the web scaffold, so authorization (AUTH-001) would wait on frontend tooling it
does not use. The web criterion moved unchanged to WEB-001; RI-006 now depends on WEB-001. No criterion
was removed or weakened.

## D-010 (2026-11-18) Move the S3 adapter criterion from DATA-002 to a new DATA-004
The first workflow runs on the local content-addressed adapter (a mounted volume in Compose). An S3 adapter
cannot be tested here without an S3 server (B-001), and writing it untested to tick a box would be worse
than saying it is not done. The criterion moved unchanged; DATA-004 is blocked on B-001.

## D-011 (2026-11-18) Audit the route template, not the concrete URL
Found by the isolation test: an outsider's long URL overflowed `audit_events.action` and turned a 404 into a
500 without recording the denial. The audit now records `METHOD /route/{template}` (no ids, bounded) and
clamps every field, so an audit write cannot fail on input length.

## D-012 (2026-11-18) Web app: npm (shared cache), same-origin API proxy, development identity until AUTH-002
npm instead of pnpm reuses the D:\npm-cache already holding Next 15.5.28 and Playwright 1.63.0 (with its
cached Chromium). The browser calls `/api/v1/*` on the web origin; Next rewrites it to the API, so no CORS
and no API URL in client code. Sign-in in the web app is the API's development identity only and is
labelled so; OIDC login (code + PKCE, HttpOnly session cookie) is AUTH-002.

## D-013 (2026-11-18) Proxy /api/v1 with a route handler, not a next.config rewrite (amends D-012)
Found by the smoke run: a rewrite's destination is resolved at `next build` and written into
routes-manifest.json, so the web build only worked against the API address it was built with (port 8000).
`src/app/api/v1/[...path]/route.ts` now forwards at request time to `PAP_API_URL`, streaming bodies both ways
and dropping hop-by-hop headers. One build runs against any API address, which Compose and any deployment need.

## D-014 (2026-11-18) Reports are regenerated on request, not stored
`report.json` is built from rows that never change after the job succeeds (results, episodes, mapping
revision, artifacts, job provenance) and serialized deterministically (sorted keys and lists, no generation
time), so regenerating gives the same bytes; the sha256 of those bytes identifies the report (X-Report-SHA256,
and named inside the HTML). `report.html` is a pure function of the parsed JSON. Storing a copy would add a
second source of truth without making the report more reproducible. Each download is audited with its digest.

## D-015 (2026-11-18) dev_stack supervises the worker
If the worker exits, dev_stack starts a new one (as a Compose restart policy would) and writes its PID to
`<state>/dev-stack/worker.pid`; the e2e recovery test kills that PID mid-job. A `--stop-file` lets scripts stop
the stack cleanly, PostgreSQL included (a forced kill on Windows leaves pgserver's postgres running), and
`--state-dir` keeps smoke runs apart from a developer's stack.

## D-016 (2026-11-18) Security scanners run as digest-pinned images, with our own Semgrep rules
gitleaks 8.30.1, Semgrep 1.183.0 and Trivy 0.76.1 run in CI as container images pinned by digest rather than
through their GitHub Actions: third-party action tags can be re-pointed (it happened to trivy-action in 2026),
an image digest cannot, and gitleaks-action needs a licence key for organization accounts. Versions are at
least two weeks old when chosen. Semgrep runs only `.semgrep/rules.yml` (registry packs are under the Semgrep
Rules License, which the integration registry does not accept); each rule has an annotated sample that
`scripts/check_semgrep_rules.py` checks, because `semgrep --test` crashes on Windows paths.

## D-017 (2026-11-18) Override next's bundled postcss
Trivy found next 15.5.28 pinning postcss 8.4.31 (CVE-2026-45623, CVE-2026-73646, fixed in 8.5.12/8.5.18).
`overrides.next.postcss = 8.5.33` (the version the rest of the tree already uses); npm ci, unit tests and the
build pass. Remove the override when next ships a fixed postcss.

## D-018 (2026-11-18) One image for API and worker; engine built inside it
api.Dockerfile builds OpenMHS from engine.lock.json (fetch by commit, `git rev-parse` check, `cargo build
--locked`) and records the digest that build produced in /app/.engine/build.json; Rust release builds are not
bit-identical across machines, so the commit pins behaviour and each platform has its own digest (D-002).
The worker is the same image with another command, so the API's /healthz engine check covers the worker's
binary too. Services run as non-root with read-only root filesystems; only /data is writable.

## D-019 (2026-11-18) Browser sign-in: the web server is the OIDC client; tokens stay server-side
The Next.js server runs authorization code + PKCE with openid-client (certified RP library) and keeps the
access token in an AES-256-GCM sealed, HttpOnly, Secure, SameSite=Lax cookie (keys derived with HKDF from
PAP_SESSION_SECRET; session and sign-in transaction cookies sealed for different purposes). The /api/v1 proxy
attaches the token and discards any Authorization header the browser sends, so page scripts can neither read a
token nor choose an identity; browser cookies are never forwarded to the API. Access tokens are requested for
the API audience with a resource indicator (RFC 8707). No refresh tokens yet: the session ends with the access
token (capped at 8 h). Tests use oidc-provider (certified OP implementation) because Keycloak needs Docker.
Rejected: tokens in sessionStorage/localStorage (readable by any script on the page), NextAuth/Auth.js (another
session layer and adapter for one provider type we already handle in ~150 lines with a certified library).

## D-020 (2026-11-18) Split OBS-001: application instrumentation now, the collector stack later (OBS-002)
All three OBS-001 criteria are about what the API and worker emit (JSON logs, metrics, one trace from request
to engine), which can be built and tested without Docker; only the collector, Prometheus server and dashboards
need Compose. OBS-001 now depends on RI-003 instead of INF-003, with its criteria unchanged; the infrastructure
part is the new OBS-002 (depends on INF-003). Nothing was weakened, as with D-009.
Telemetry records operational facts only: ids, route templates, status codes, durations, states, engine outcome
codes. FastAPI 0.163 ships built-in OpenTelemetry whose server span records the concrete URL (tenant slugs and
ids); it is switched off (`telemetry={...False}`) and the `observe` middleware makes the single request span.
Engine telemetry comes from a bridge observer hook (command, timing, outcome; never arguments or output), so the
bridge stays free of OTel/Prometheus. Job-state gauges are read from the database at scrape time so they are
right across processes; job and engine metrics are served by the worker on PAP_WORKER_METRICS_PORT.

## D-021 (2026-11-18) S3 adapter tested against SeaweedFS run natively, not mocked (unblocks DATA-004)
DATA-004 was blocked on Docker (B-001) for an S3 server. SeaweedFS (the registry's preferred self-hostable S3,
Apache-2.0) ships a Windows binary, so the tests start a real server per session instead of using a mock such as
moto, which would test our assumptions about S3 rather than S3. The adapter spools the upload to a temporary
file so the size limit and SHA-256 are known before sending, skips the upload when the key exists (write-once),
sends the SHA-256 checksum for the server to verify, and checks the digest of every object it reads.
