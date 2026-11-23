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

## D-022 (2026-11-18) Graphify installed as a personal, optional tool, not the way its installer does it
Reviewed by running `graphify claude install` in a throwaway clone and diffing: it adds two PreToolUse hooks to
the committed `.claude/settings.json` with an absolute path to this machine's executable (breaks for anyone
else and CI, and leaks a local path), a CLAUDE.md section that makes graph queries mandatory, a stray
`.graphify-bak`, and drops the final newline. The hooks are advisory (they add context, never block). Installed
instead: the same hooks in `.claude/settings.local.json` (gitignored), a short CLAUDE.md note that keeps it
optional and says to read the source before relying on an answer, and `.graphifyignore` excluding var/, the
engine build, evidence files (csv/jsonl/sqlite/mcap/db3), evaluation results and .env files. The graph
(`graphify-out/`, gitignored) is built with `graphify update .` (AST only); no LLM API key is configured, so
no code leaves the machine. Checked: no evidence fragment, local data path or secret in graph.json.

## D-023 (2026-11-19) Runtime base images track the newest official rebuild; no package managers at run time
Found by the first CI run: the Trivy image scan failed with 46 fixable HIGH/CRITICAL findings in the Debian
packages of python:3.12.11-slim-bookworm. Scanning candidates straight from the registry (Trivy needs no Docker
for that) gave 0 for python:3.12.16-slim-bookworm and 0 OS findings for node:22.23.5-bookworm-slim; the node
image's remaining 10 were all inside its bundled npm, which the web server never runs, so the runtime stage
deletes npm, npx, corepack and yarn. Official base images are an exception to "versions at least two weeks
old": their rebuilds are the security fixes, so waiting keeps known vulnerabilities. They are still pinned by
digest; bumping them is a reviewed change. Bookworm (not trixie) keeps the runtime on the same Debian release
as the engine build stage (glibc).

## D-024 (2026-11-21) Design direction "Precision Industrial", written down in DESIGN.md
The product brief asks for engineering software that reads like Linear, Foxglove and Sentry rather than a generic
dashboard. DESIGN.md is the contract: tokens, type, spacing, shell, per-module interaction patterns, chart and
writing rules, anti-patterns. Two departures from the brief's palette: the brief merged "unknown" and "warning"
into one amber, but the product separates contradiction (warning) from unknown, so unknown keeps its own colour;
and the brief's tertiary grey was raised to pass AA on the sunken surface. Honesty rules outrank visual ones:
modules that are not built are not in the navigation, and concept imagery never appears in the application.
Fonts come from the `geist` package so builds and air-gapped installs do not fetch from Google.

## D-025 (2026-11-21) Design skills: reviewed, installed pinned, without their hooks or binaries
Reviewed both repositories in throwaway clones (D:/openmhs-tmp/review). Impeccable (pbakaus/impeccable,
b49177d, Apache-2.0): useful audit and critique playbooks, but `npx impeccable install` registers SessionStart,
PostToolUse(Edit|Write) and Stop hooks that run its launcher on every edit outside model approval, and the
launcher downloads a native engine on first use (checksum-verified against a manifest, but not reviewable here).
Taste Skill (Leonxlnx/taste-skill, f6b7657, MIT): a marketing-website skill (hero entrances, photographs,
shader effects) of 38 MB whose SKILL.md registers a Stop hook running `node scripts/gate.mjs` for up to 600 s.
Decision: `scripts/install-design-skills.sh` fetches exactly those commits and copies skill files into
`.claude/skills/` (gitignored): Impeccable's SKILL.md and reference playbooks only (no launcher, so the skill takes
its documented "launcher unavailable" path and reads PRODUCT.md/DESIGN.md directly); Taste Skill whole, for a
future public website only. No installer runs, no hook is registered, nothing is downloaded at use. DESIGN.md
stays the authority: Impeccable's `document`/`init` commands, which write DESIGN.md/PRODUCT.md, are not used.
The measurable part of the audit is axe-core in the browser suite (`e2e/a11y.spec.ts`).

## D-026 (2026-11-21) Execution scope: commands only to simulated devices, enforced in code
The owner directs the platform to execute workflows ("no physical hardware writes"). The invariant "observation
only" becomes: the platform may invoke actions only on devices in an environment the operator configured as
`simulated` AND whose own description declares it simulated; for every other device it may discover and read,
never write. Both checks run in the executor immediately before each dispatch and are covered by tests; a
mismatch fails the step without sending anything. The API never talks to an arbitrary URL: environments are
chosen from an operator-configured list (`PAP_ENVIRONMENTS`), which closes the server-side request forgery a
user-supplied endpoint would open. Nothing sits in a real-time control path.

## D-027 (2026-11-21) Devices are described by W3C WoT Thing Descriptions; first adapter is LabThings
Device and capability discovery uses the W3C Web of Things Thing Description, the format LabThings-FastAPI
serves (`/thing_descriptions/`, one TD per Thing; actions are POSTed and return an invocation resource that is
polled). The virtual laboratory is built with labthings-fastapi 0.3.0 (MIT, 2026-08-17) in its own uv project
(`runtimes/virtual-lab`, own lock), so its FastAPI/pydantic pins never constrain the platform. The adapter SDK
(`packages/device-sdk`) defines the platform side (discover, read, invoke) so ROS 2, OPC UA or SiLA adapters can
be added behind the same interface later.

## D-028 (2026-11-21) Workflow durability: journal before dispatch, at-most-once unless the action is idempotent
Workflow runs use the same PostgreSQL lease pattern as evaluation jobs. Each step is journalled as `dispatching`
with a request id before the HTTP call and as `completed`/`failed` after. On resume after a crash, a step left in
`dispatching` is re-sent only when the action accepts a `request_id` (the instrument deduplicates it, so the effect
happens once); otherwise the step and run stop as `outcome_unknown` for a human to decide, because re-sending a
non-idempotent command to an instrument could repeat a physical effect. The run's verified result comes from
`openmhs outcome verify` on an RFC 0004 contract and the independent instrument's evidence, never from the
platform's own comparison.

## D-029 (2026-11-22) The ROS observer has no command surface, by construction and by test
The OpenAMRobot workspace is "observe, never drive": the observer (runtimes/ros-observer) is a node that only
subscribes, plus one client for one service type (controller_manager ListControllers, a query). Its Thing Descriptions
are built from a structure with no field for an action, so none can be declared; the HTTP server answers GET and HEAD
only; a source-scan test fails if the code ever mentions a publisher, an action client or server, a parameter write or a
subprocess; and the real-graph test reads `ros2 node info` to check that the node's publishers are rclpy's own defaults
and its only client is list_controllers. An observer device also declares no `simulated` property, so the executor's
safety check would refuse it even if a workflow could name it (it cannot: no action exists to name). Freshness is judged
on a monotonic clock because the WSL wall clock steps back about a second every half minute. NaN and infinities become
null because a mock sensor really did report NaN and a strict JSON parser rejects the whole response.

## D-030 (2026-11-22) Recorded runs are evidence only as far as their provenance goes
The platform does not run the #177 scenario (that would publish /cmd_vel and touch controller ownership); it ingests what
the user's own scripts recorded. runs.json says, for every run, which arm it belongs to and WHY (script, run name, time),
and whether the software state is exactly known: only two runs are on the committed fix 505d17a, the others ran on the
fix branch's working tree minutes before the commit. The new scenario script writes its own identity (commit, dirty
flag, configuration, ROS/RMW, host) beside an MCAP bag. With 4 vs 7 runs the engine's answer is insufficient evidence
and the platform reports exactly that: min_known stays at its default of 30. The `site` field carries the procedure
(publisher kill vs killing a downstream node) so mixed procedures are visible per stratum, not hidden in one rate.

## D-031 (2026-11-22) Assistants get a viewer credential; the approval gate is the platform's roles, not the tool layer
The tool layer (packages/agent-tools) has typed tools over the platform's own API, run with the caller's credential.
Thirteen tools: twelve read-only, one write (propose_experiment) that only records a proposal. Approval needs the engineer
role, so an assistant holding a viewer credential cannot approve however it behaves; the platform refuses with 403. The
X-PAP-Channel header only labels a proposal as having come through the tools (shown in the UI); it is not a security
control. Approval queues an ordinary run through the unchanged executor and is refused (409) unless the environment is
simulated. The investigation is rule-based and says so in its output; no language model is integrated, none was run, and
no paid service is called. MCP is implemented by hand for the tools capability only (initialize, ping, tools/list,
tools/call over newline-delimited JSON-RPC on stdio): the official SDK is at 2.x, a major version newer than the API this
work could verify, and the part needed here is small and tested over a real pipe.

## D-032 (2026-11-22) Observability stays optional and uses unmodified images
Compose profile `observability`: OpenTelemetry Collector 0.164.0 and Prometheus v3.15.1, pinned by version and digest
(both older than two weeks), configs in infrastructure/observability. Grafana, Loki and Tempo (AGPL-3.0) are not
included; they may only ever run as separate, unmodified services of the operator's own.

## D-033 (2026-11-22) The official MCP SDK was verified, and is still not adopted
`mcp` 2.3.0 (MIT, 2026-10-02) was run as a client against our stdio server (`scripts/mcp_sdk_interop.py`, in an isolated
`uv run --isolated --with mcp==2.3.0`, so it never enters the platform's lock). It negotiates, lists all tools with their
annotations, and treats bad input and unknown tools as errors. It found one real defect, fixed: the server echoed any
protocol version it was asked for instead of answering with the one it implements (2025-06-18). Adopting the SDK as the
server would add starlette, uvicorn, sse-starlette, pyjwt, httpx2, jsonschema and opentelemetry-api to a package whose job
is a small tools-only stdio server; the interoperability evidence is the reason to keep the small server, and the reason
to revisit is a need for streamable HTTP, OAuth or resources/prompts.

## D-034 (2026-11-22) A robot model is imported, never drawn; a recording is evidence with provenance
The registry stores upstream's own expanded URDF and the meshes it references byte for byte, addressed by digest, with
repository, commit and licence (OpenAMRobot: CERN-OHL-P-2.0 for CAD-derived geometry; upstream's NOTICE and LICENSING are
kept beside the files). Unreferenced files, `..`, `file://`, DTDs and non-STL meshes are refused. A recording is an MCAP
file whose track is decoded by `mcap-ros2-support` (no ROS needed) on the recording's own clock: the running maximum of
`/clock`, because the pre-fix bag's clock moved backwards (reported as a warning event, never smoothed away). Wheel joint
positions are constant 0 in both bags while the base drives: the twin draws exactly that and says so. Events carry their
rule and source topic; the verdict beside them is the engine's, never recomputed from the track.

## D-035 (2026-11-22) The assistant is the existing tool registry, run as the caller
The twin's assistant calls `POST /orgs/{org}/assistant/tools/{tool}`, which runs the SAME typed tools the MCP server serves
(read-only ones only) against this API with the caller's own Authorization header, so roles and isolation are unchanged.
`propose_experiment` is not reachable there. The explanation is rule-based, cites evidence ids, separates the recording's
measurement from the engine's verdict, and lists what is not known. HTTP and MCP return byte-identical answers (tested).

## D-036 (2026-11-22) Simulation execution is a host contract plus the existing workflow engine
A simulation host is a LabThings Thing (`pap.simulation-host/1`) in front of any simulator; the platform never learns
which. Scenarios are an operator-owned catalog of fixed argument lists with parameter JSON Schemas, outputs and
artifacts; the platform sends a scenario id and validated parameters, never a command. An experiment version is an
immutable spec; approval of a version compiles it to ordinary workflows (one per arm) and queues trials through the
unchanged workflow service, so the durable worker, the simulated-only safety check (D-026), the journal and the engine's
verdict apply without a second execution engine. A host reports only what the scenario's own result file contains.
Because the host's claim ("the run completed") is not the robot's claim, the experiment views show the engine's verdict
(satisfied/violated) and never the 'contradiction' class an instrument report would imply. Camera-configuration
comparisons are experiments with several arms; the scenario that measures visibility belongs to the simulation owners.


## D-037 (2026-11-22) Experiment specs pin what can change underneath them; approval names a checksum
The spec (`pap.experiment-spec/1`) records the simulator identity and a digest of the scenario's listed definition as the
host reported them when the version was created, so an operator who edits a scenario without bumping its version, or
swaps the simulator, invalidates approval instead of silently changing what runs. The approver sends the checksum they
reviewed; the platform accepts the decision only for that exact checksum. Seeds are trial inputs (a scenario declares an
integer `seed` parameter to accept them), so trials with different seeds are separate workflows (one per arm and seed)
rather than one workflow per arm: a workflow's definition is its exact input. Time limits the platform can enforce are
budgets checked before approval (trials, wall time from the scenario's own maximum); the step timeout during a run is
the scenario's maximum plus a margin, because only the host can stop a running simulator (D-036). The selftest host
gains a kinematic `selftest-drive` scenario (a point base integrating its last command; labelled not a simulator) so the
whole journey, including a recording in the twin, is tested without Gazebo; its telemetry is computed by that stated
model, not replayed from another run. `jsonschema` is added to the API to validate parameters before approval.

## D-038 (2026-11-22) The Gazebo host refuses rather than degrades, and its pre-fix arm is a described working tree
A real Gazebo run needs memory this machine often lacks and shares a ROS workspace with other work. The host's command
checks before starting anything (memory inside WSL and on Windows, disk, no Gazebo running, a clean checkout) and refuses
with the reason; the platform shows that as a failed trial with nothing measured. The pre-fix arm is the fix commit with
the two wiring files the fix changes taken from origin/main for one run (the existing `run_main.sh`); the run identity
names the commit, the dirty tree and the files, so it is never presented as a clean build of 69847ab. Real Gazebo tests are
opt-in (PAP_REQUIRE_GAZEBO=1 or PAP_RUN_GAZEBO=1): a default full suite must not start simulations in a shared workspace.

## D-039 (2026-11-23) The agentic harness is a Strands agent behind the platform's own permissions, in its own project
AGENTS.md asks for a recorded decision before adopting an LLM framework. The user asked for a Strands-based harness.
It lives in `packages/agent-harness`, a separate uv project, so Strands' dependency set (openai, mcp, boto3,
opentelemetry) never enters the API's environment. It uses only the platform's agent tools (`pap_agent_tools`), runs as
the caller, can record a run request or a proposal but never approve, start or command (D-026, D-037), and stops before
a model call on a step limit, timeout, cancellation, session budget or per-experiment budget. Keys come from the
environment and are never written. Its tests use a labelled scripted model and verify orchestration only; real-model
quality is claimed only from real runs with the user's spending authorization.

## D-040 (2026-11-23) The harness reaches the website as a subprocess of the API, read-only, with drafts a person files
The owner asked for the agent to work in the website with a real model. The API must not gain a language-model framework
(D-039 keeps Strands in its own uv project), so `app/agent/sessions.py` runs `pap-harness ask` as a subprocess, as the
signed-in caller (their credential, passed by environment, not by argument; the question follows `--` so it is never an
option). The model key is read by the harness from `PAP_LLM_*` in the server's environment: never a setting, never
returned, scrubbed from anything stored, never sent to a browser. Asking costs money, so it needs the engineer role and is
bounded three ways: a per-session cap, a daily cap over the server, and a limit on sessions running at once. The website
never passes `--allow-requests`. At most the engineer may tick a box so the agent can DRAFT a follow-up (`--draft-requests`):
the draft stays in the trace, and a person files it with a click, as themselves; filing is an ordinary proposal and still
needs a different person to approve. With no model configured the page still answers the fixed questions and a
rule-based investigation of a laboratory run, labelled "no model"; that is the scripted fallback and is never presented as
inference. A deterministic note is appended when evidence is simulated and the model's answer does not say so.

## D-041 (2026-11-23) A second person approves every proposed run; a fault is a journaled step; a run has a report
(1) Approving a workflow proposal now refuses its own proposer (403 `separation_of_duties`), as D-037 does for Studio
experiments; withdrawing your own proposal stays allowed. (2) The failing laboratory case is a second built-in template,
`dispense-with-fault`: the same procedure and tolerance with two extra visible steps that inject and clear a simulated
fault through the virtual laboratory's own simulation controls (a discovered, simulated-only device). The pump still
reports the volume it was commanded and the balance measures what arrived; nothing is edited afterwards and the bench is
left healthy. (3) `GET /workflow-runs/{id}/report.json|html` formats a run's stored records (procedure digest, executed
steps, reported vs independently verified, engine provenance, follow-up proposals). It computes nothing and has no
generation time, so the same run always yields the same bytes.

