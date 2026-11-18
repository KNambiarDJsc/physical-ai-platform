# Open-source integration registry

Every project considered for the platform: what it would do, where the boundary is, and the decision.
Rule: nothing is installed unless an acceptance criterion needs it; adoption requires a verified license and
a pinned version (the lock file is the bill of materials: `uv.lock`, later `pnpm-lock.yaml`, `engine.lock.json`).

**License column**: "verified (metadata)" = read from the installed package's metadata on 2026-11-18;
"stated, verify before adoption" = recorded from the project's public repository without re-checking at a
pinned revision; such entries must be re-verified before any adoption. Dataset, model-weight and asset
licenses are separate from code licenses and are noted where known to differ.

Status values: **adopted** (in a lock file), **dev-only** (tests/tooling, never shipped), **planned**
(needed by a scheduled feature), **candidate** (possible future integration), **reference** (study only).

## Adopted now (minimum set for the first Release Intelligence workflow)

| Project | Function / boundary | Version (locked) | License | Commercial note | Decision rationale |
|---|---|---|---|---|---|
| OpenMHS (github.com/KNambiarDJsc/Open-MHS) | Evaluation engine; CLI boundary (ARCHITECTURE.md) | commit e9ef873 | Apache-2.0 (verified, LICENSE) | Permissive; keep NOTICE/attribution; `conditions_of` copied with attribution | The canonical engine (directive) |
| FastAPI (github.com/fastapi/fastapi) | HTTP API | 0.163.2 | MIT verified (metadata) | Permissive | Directive stack; OpenAPI generation |
| Starlette | ASGI under FastAPI | 1.10.0 | BSD-3-Clause verified | Permissive | Transitive |
| Uvicorn | ASGI server | 0.54.0 | BSD-3-Clause verified | Permissive | Standard FastAPI server |
| Pydantic / pydantic-settings | Models, validation, JSON Schema, env config | 2.14.3 / 2.16.3 | MIT verified | Permissive | Source of contract schemas |
| SQLAlchemy | ORM / SQL | 2.0.58 | MIT verified | Permissive | Directive stack |
| Alembic | Migrations | 1.20.1 | MIT verified | Permissive | Directive stack |
| psycopg 3 (+ psycopg-binary) | PostgreSQL driver | 3.3.9 | **LGPL-3.0-only** verified | Used unmodified via import: permitted in proprietary products; ship license text; binary wheel bundles libpq (PostgreSQL License) and OpenSSL (Apache-2.0) | Only maintained PG3 driver with SQLAlchemy 2 async/sync support; alternative asyncpg (Apache-2.0) if LGPL is rejected |
| python-multipart | Streaming multipart uploads | 0.0.34 | Apache-2.0 verified | Permissive | Required by FastAPI `UploadFile` |
| PyJWT [crypto] + cryptography | OIDC access-token validation (JWKS) | 2.15.1 / 50.0.2 | MIT / Apache-2.0 OR BSD-3 verified | Permissive | Decision D-007 (instead of Authlib) |
| PostgreSQL (postgres.org) | Platform metadata store | image `postgres:16` (Compose) | PostgreSQL License (stated) | Permissive | Directive stack |
| SQLite (sqlite.org) | Inside the engine only | bundled in OpenMHS (rusqlite) | Public domain (stated) | None | Engine's store |

## Dev-only (never shipped)

| Project | Function | Version | License | Note |
|---|---|---|---|---|
| uv (astral-sh/uv) | Python env + lock | 0.7.11 | MIT OR Apache-2.0 (stated) | Lock file = Python SBOM |
| Ruff | Lint + format | 0.12.12 | MIT verified (classifier) | |
| mypy | Static types | 1.20.2 | MIT verified | strict on bridge and API |
| pytest | Tests | 8.4.2 | MIT verified | |
| httpx | API test client | 0.28.1 | BSD-3-Clause verified | |
| pgserver (github.com/orm011/pgserver) | Throwaway real PostgreSQL for tests without Docker | 0.1.4 | **not declared in package metadata; verify** | Dev/test only (decision D-006); never in images. Replace with testcontainers once Docker is available |
| Graphify (github.com/Graphify-Labs/graphify, `graphifyy`) | Optional code knowledge graph | 0.9.97 (uv tool, global) | verify before project install | Optional; not in any gate; project install pending review (blocker B-003) |

## Planned (scheduled feature needs it; adopt when that feature starts)

| Project | Function / boundary | Feature | License | Notes / evaluation criteria |
|---|---|---|---|---|
| Next.js (vercel/next.js) | Web app, App Router | INF-002, RI-006 | MIT (stated) | Pin to the version already cached for AI Studio (15.5.28) unless a security advisory says otherwise |
| React | UI | RI-006 | MIT (stated) | |
| shadcn/ui (shadcn-ui/ui) | Copied component source | RI-006 | MIT (stated) | Code is copied into the repo: keep license header |
| Radix UI primitives | Accessible primitives | RI-006 | MIT (stated) | |
| TanStack Query / Table | Server state, dense tables | RI-006/007 | MIT (stated) | |
| Apache ECharts | Interval and rate charts | RI-006 | Apache-2.0 (stated) | Renders engine numbers only |
| openapi-typescript (openapi-ts) | TS types from OpenAPI | RI-005 | MIT (stated) | Generated client checked for drift |
| React Hook Form + Zod | Forms, client validation | RI-006 | MIT (stated) | |
| Lucide | Icons | RI-006 | ISC (stated) | |
| Vitest, Playwright | Web tests | RI-006, E2E-001 | MIT, Apache-2.0 (stated) | Playwright 1.63.0 has a cached Chromium on this machine |
| Tailwind CSS | Styling | RI-006 | MIT (stated) | |
| Caddy (caddyserver/caddy) | Reverse proxy in Compose | INF-003 | Apache-2.0 (stated) | |
| Docker Compose | Local stack | INF-003: `docker-compose.yml` (v2.39 config-validated) | Apache-2.0 (stated) | Images: postgres 16.10, python 3.12.11-slim, rust 1.89.0-slim, node 22.16.0-slim, uv 0.7.11, all tag+digest pinned. Not run locally (B-001) |
| Keycloak (keycloak/keycloak) | Reference OIDC provider for self-hosted installs | AUTH-001 live test | Apache-2.0 (stated) | Not embedded; any OIDC IdP works |
| SeaweedFS (seaweedfs/seaweedfs) | S3-compatible object store for self-hosting | DATA-002 S3 adapter | Apache-2.0 (stated) | Preferred over MinIO (AGPL-3.0, community edition in maintenance) and Garage (AGPL-3.0) for redistribution in a commercial self-hosted bundle; the adapter speaks plain S3, so customers may bring any S3 |
| boto3 / botocore | S3 client | DATA-002 | Apache-2.0 (stated) | Only when the S3 adapter is built |
| OpenTelemetry Python / Collector | Traces, metrics over OTLP | OBS-001 | Apache-2.0 (stated) | |
| Prometheus | Metrics | OBS-001 | Apache-2.0 (stated) | |
| Grafana / Loki / Tempo | Dashboards, logs, traces | OBS-001 | **AGPL-3.0** (stated) | Run as separate, unmodified services; never embed or link; customers may already run their own |
| Trivy | Image and dependency scan in CI | SEC-001: 0.76.1, image `aquasec/trivy` by digest | Apache-2.0 (stated) | Run as the container image, never `aquasecurity/trivy-action` (its tags were hijacked in 2026). Local run: found and fixed postcss in next |
| Semgrep (CE engine) | Static analysis in CI | SEC-001: 1.183.0, image `semgrep/semgrep` by digest | LGPL-2.1 engine (stated); registry rules under the Semgrep Rules License | Only our own rules (`.semgrep/rules.yml`, self-tested by `scripts/check_semgrep_rules.py`); no registry packs. Run as a separate tool, not linked |
| gitleaks | Secret scan in CI | SEC-001: 8.30.1, image `ghcr.io/gitleaks/gitleaks` by digest | MIT (stated) | Binary, not `gitleaks-action` (which needs a licence key for organization accounts). `scripts/check_secrets.py` is the local guard |
| Hypothesis | Property tests (mapping, canonical JSON) | DATA-003 | MPL-2.0 (stated) | Dev-only |
| Schemathesis | OpenAPI fuzzing | SEC-001 | MIT (stated) | Dev-only |
| testcontainers-python | Ephemeral PostgreSQL/S3 in tests | once Docker is available | Apache-2.0 (stated) | Replaces pgserver |

## Considered and deferred

| Project | Why not now | Revisit when |
|---|---|---|
| Procrastinate (procrastinate-org/procrastinate) | Second job table and states outside Alembic; our job is a domain entity (D-005) | Periodic jobs, several queues |
| Authlib | API only validates tokens (D-007) | API runs OAuth flows itself |
| full-stack-fastapi-template (MIT) | Reference for layout and auth patterns; its SQLModel and password auth do not match OIDC + SQLAlchemy | Reference only |
| Apache Arrow, Polars, DuckDB | No columnar workload yet; CSV/JSONL episodes are small | Fleet-scale evidence, Parquet input |
| MinIO, Garage | AGPL-3.0 (see SeaweedFS row) | Customer already runs one: supported through the S3 adapter, not bundled |

## Robotics data and interoperability (candidates)

| Project | Intended function | Boundary | License | Decision |
|---|---|---|---|---|
| foxglove/mcap | Read MCAP recordings | Inside OpenMHS importers or a customer-side converter, not the API | MIT (stated) | Candidate; OpenMHS research bridge already uses `mcap` |
| ros2/rosbag2 | rosbag2 format | Customer side; OpenMHS `coresense_aerostack2` importer reads rosbag2 SQLite | Apache-2.0 (stated) | Use OpenMHS importers; upload their events |
| ros2/ros2, rclpy | Live ROS 2 | Never in the platform (observation of recordings only) | Apache-2.0 (stated) | Reference |
| huggingface/lerobot | Policy rollouts, datasets | OpenMHS `policy_rollouts` importer | Apache-2.0 code (stated); dataset/weights licences vary | Candidate via OpenMHS-native events |
| Rerun (rerun-io/rerun) | Multimodal replay of evidence | Viewer link from an episode | MIT OR Apache-2.0 (stated) | Evaluate after E2E-001 |
| Lichtblick | Foxglove-Studio fork viewer | External viewer link | MPL-2.0 (stated) | Reference |
| RViz, PlotJuggler | Desktop viewers | Customer tools | BSD-3 / MPL-2.0 (stated) | Reference |
| three.js, urdf-loaders | Robot model rendering | Future episode view | MIT / Apache-2.0 (stated) | Not in first milestone |

## External robotics systems and agent runtimes (evidence sources only)

| Project | License | Decision |
|---|---|---|
| OpenRAL (OpenRAL/openral) | not verified | Candidate evidence source; adapter not implemented; do not claim compatibility |
| strands-labs/robots, robots-sim | not verified | Candidate evidence source |
| strands-agents/sdk-python | Apache-2.0 (stated) | Reference; no LLM framework in the platform |
| modelcontextprotocol/python-sdk | MIT (stated) | Deferred; an MCP read API over results is a Phase 6 idea |
| Open-RMF | Apache-2.0 (stated) | Candidate fleet evidence source (task states) |
| MoveIt 2 | BSD-3-Clause (stated) | Evidence source (action results) via rosbag2 |
| Nav2 | Apache-2.0 (stated, some files differ) | Evidence source via rosbag2 |
| ros2_control | Apache-2.0 (stated) | Evidence source |
| Eclipse Zenoh | EPL-2.0 OR Apache-2.0 (stated) | Candidate live transport for a future edge agent; not now |

The platform never takes over their execution or safety responsibilities.

## Simulation and policy evaluation (workload sources)

| Project | Code license (stated) | Asset / weight caveat | Decision |
|---|---|---|---|
| MuJoCo | Apache-2.0 | — | Candidate workload; importer not implemented |
| MuJoCo Menagerie | per-model licences | each model has its own | Check per model before use |
| Gazebo (gz-sim) | Apache-2.0 | — | Existing OpenMHS Gazebo fixtures reused |
| Isaac Lab | BSD-3-Clause | Isaac Sim itself is under NVIDIA's licence | Candidate; do not bundle Isaac Sim |
| Genesis | Apache-2.0 | — | Candidate |
| openpi | Apache-2.0 | weights have own terms | Workload only |
| OpenVLA | MIT code | weights built on Llama 2 (Llama 2 Community License) | Workload only; review weight licence |
| Isaac GR00T | Apache-2.0 code | NVIDIA model licence for weights | Workload only |

## Benchmarks (reproducible workloads)

LIBERO (MIT), robosuite (MIT), robomimic (MIT), ManiSkill (Apache-2.0, assets vary), RoboCasa (MIT, assets
have own terms), SimplerEnv (MIT), RoboTwin, RoboVerse (licences not verified). All: candidate workloads;
dataset and asset licences reviewed independently before any redistribution of results or data.

## Industrial and scientific integrations (future evidence sources)

open62541 (MPL-2.0), opcua-asyncio (LGPL-3.0), Eclipse Mosquitto (EPL-2.0/EDL-1.0), pymodbus (BSD-3),
PyVISA (MIT), Bluesky and ophyd (BSD-3). All stated, not verified; none adopted. OPC UA and laboratory
instrument sources fit the RFC 0004 evidence-record format (independent measurements) and are the most
natural next adapters after a customer asks.

## Product architecture references (study only, no code copied)

| Project | License | What to learn |
|---|---|---|
| Grafana | AGPL-3.0 | Dense dashboards, time-range navigation |
| Sentry | FSL (source-available, not open source) | Issue grouping, release health; **no code reuse** |
| Langfuse | MIT core, `ee/` under commercial licence | Trace drill-down, evaluation runs vs datasets |
| MLflow | Apache-2.0 | Run comparison UI, artifact lineage |
| OpenAMRobot AI Studio (same owner) | no LICENSE file yet | Contract generation (Pydantic → JSON Schema → TS), FastAPI layout, Playwright setup. Patterns only; no robotics control code |
