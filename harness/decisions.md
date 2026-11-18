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
