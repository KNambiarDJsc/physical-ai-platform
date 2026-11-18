# Architecture

Modular monolith (FastAPI) + a separately executed evaluation worker + a Next.js web app. The OpenMHS Rust
binary, pinned by commit and SHA-256, is the only evaluation implementation.

```
customer evidence (CSV / JSONL / OpenMHS events)                       never: commands to robots
        │ upload (streamed, size-limited, sha256-addressed, immutable)
        ▼
 ┌────────────── API (FastAPI) ──────────────┐        ┌───────────── worker (same codebase, own process) ─────────────┐
 │ auth (OIDC) · orgs · projects · releases  │  jobs  │ claim job (FOR UPDATE SKIP LOCKED + lease)                    │
 │ artifacts · mappings · evaluation jobs    │ ─────▶ │ load inputs, check sha256                                     │
 │ results · episodes · reports · audit log  │  (PG)  │ mapping → episodes + RFC 0004 evidence + RFC 0005 events      │
 └───────────────┬───────────────────────────┘        │ per episode: openmhs outcome verify --json   (Rust verdict)  │
                 │                                    │ openmhs ops ingest → job store (SQLite, per job)             │
                 │                                    │ openmhs ops compare --json (reported, verified[, paired])    │
                 │                                    │ openmhs ops incidents --json                                 │
                 │                                    │ persist results + evidence bundle + provenance               │
                 ▼                                    └───────────────────────────────────────────────────────────────┘
          PostgreSQL (metadata, results)       object storage (source artifacts, events.jsonl, ops.sqlite, reports)
                 ▲
                 │ REST (OpenAPI → generated TypeScript client)
          Next.js web app
```

## Components

| Path | Role |
|---|---|
| `packages/openmhs-bridge` | The only code that runs the engine. Checks binary digest, runs with an argument list, timeout and output cap, parses JSON into typed models, attaches engine provenance. No knowledge of the database. |
| `services/api/app` | FastAPI app and the worker entry point (`python -m app.workers.run`). Domain packages: `auth`, `organizations`, `projects`, `releases`, `evidence`, `ingestion` (mapping), `evaluations` (jobs, pipeline, reports), `outcomes`. |
| `services/api/migrations` | Alembic. Every schema change is a migration; tests run upgrade → downgrade → upgrade. |
| `packages/contracts` | Generated: JSON Schemas of mapping configs, episodes and reports; OpenAPI document; TypeScript client. Source of truth is the Pydantic models in the API. |
| `apps/web` | Next.js App Router UI. Reads only the API. Computes no statistics. |

## The engine boundary (versioned)

The platform talks to OpenMHS through its CLI with `--json`, the same boundary OpenMHS's own Python
importers use. Pinned in `engine.lock.json` (repository, commit, expected interface versions). Interfaces used:

| Call | Input | Output used |
|---|---|---|
| `openmhs --json outcome verify --contract C --evidence E` | RFC 0004 contract + evidence records (JSONL) | verdict, reasons, per-condition results and observed values; exit 0/3/4 = satisfied/violated/unknown |
| `openmhs --json ops ingest --store S F` | RFC 0005 events, `openmhs.deployment/0.1` manifests, `openmhs.artifact/0.1` refs | accepted/duplicate/conflict/rejected counts, rebuild summary (`rules_version`) |
| `openmhs --json ops compare --store S --task-type T --a A --b B [--verified] [--paired]` | release labels | `Comparison`: arms (counts, Wilson CI, unknown bounds, durations, goal verdicts), Newcombe difference, strata, paired McNemar, verdict, reasons, warnings |
| `openmhs --json ops incidents` / `ops show` | — | incident summaries and timelines |

Guards: the bridge refuses a binary with the wrong digest; checks `rules_version` and schema strings
against `engine.lock.json`; fails the job if ingest rejects any record or if a release selector resolves to
digests other than the ones we wrote. Upgrading the engine = new lock commit + re-run of the bridge
integration tests + recorded decision.

## Evaluation pipeline (one job)

1. **Inputs**: baseline release, candidate release, one or more artifacts per release, one mapping
   revision, evaluation config (task type, `min_known`, `margin`, paired on/off). The input checksum is
   sha256 over the canonical JSON of these ids + artifact digests + mapping digest + config + engine digest;
   it is the idempotency key.
2. **Mapping** (`ingestion`): each source row → one episode, or a row rejection with row number and reason.
   Each episode yields RFC 0005 events (`task.started`, `task.ended` with `outcome.reported`, scope,
   `scenario_id`, `deployment.manifest`) and, when the mapping declares independent measurements, RFC 0004
   evidence records plus a contract instantiated from the mapping's contract template.
3. **Verification**: `outcome verify` per episode that has a contract. The verdict, reason codes and
   condition results are copied (never recomputed) into an `outcome.verified` event `derived_from` the task.
4. **Engine store**: manifests + events → `ops ingest` into a fresh SQLite store for this job.
5. **Comparison**: `ops compare` reported and verified (and paired when scenarios match); `ops incidents`.
6. **Persist**: episodes (with outcome class), engine outputs verbatim, events file, store file and verifier
   reports as immutable artifacts, provenance (engine version/digest/commit/rules, mapping revision, input
   checksums, config).

### Outcome classes per episode (a labelled cross-tabulation, not a statistic)

| reported \ verdict | satisfied | violated | unknown (evidence present) | no independent evidence |
|---|---|---|---|---|
| succeeded | supported_success | contradiction | unknown | reported_only |
| failed / aborted / timeout / canceled | contradiction | verified_failure | unknown | reported_only |
| unknown / missing | verified_success | verified_failure | unknown | insufficient_evidence |

"No independent evidence" means the verifier returned UNKNOWN and every reason is `evidence.missing` for
every independent item, or the mapping declares no independent measurement. The verifier still runs; the
class is derived from its reason codes.

## Storage

- **PostgreSQL**: organizations, users, memberships, service credentials, projects, sites, robots, releases,
  artifacts (metadata), mapping revisions, evaluation jobs, episodes, results, audit events.
- **Object storage**: content-addressed (`sha256/<aa>/<digest>`), write-once. Local filesystem adapter for
  development; S3-compatible adapter for deployment (MinIO/Garage/SeaweedFS decision pending licence review,
  see the integration registry).
- **SQLite**: only inside the engine, one store per job, kept as an artifact for reproduction.

## Jobs

Table-backed queue in PostgreSQL (`evaluation_jobs`): states `queued → running → succeeded | failed |
cancelled`. Claim with `FOR UPDATE SKIP LOCKED`, lease with expiry and heartbeat; expired leases are
re-queued at worker start and periodically (bounded attempts). Cancellation is a flag checked between
pipeline stages and by killing the engine subprocess. The API never runs the pipeline.

## Identity and authorization

OIDC bearer tokens (JWT validated against the issuer's JWKS: signature, `iss`, `aud`, `exp`). Users are
keyed by (`iss`, `sub`). Organization membership carries the role: `admin`, `engineer`, `viewer`. Every
project-scoped route loads the project by (organization of the caller, project id); mismatches are 404.
Service credentials: random tokens, stored as SHA-256, scoped to one organization and role, revocable.
Protected writes and denials are written to `audit_events`. A `dev` auth mode (static local identities)
exists for development only and refuses to start with `PAP_ENV=production`.

## Decisions

Short log in `harness/decisions.md`; full records in `docs/decisions/`.
