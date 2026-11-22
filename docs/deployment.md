# Deploying the platform

For the person who installs and runs it for a team. Everything here is self-hosted; no part of the platform calls a
paid service. The Docker Compose stack is built and exercised in CI on every push (images, non-root users, resource
limits, smoke test, browser suites, image scan).

## What runs

| Service | Image | Role |
|---|---|---|
| `postgres` | postgres:16 (pinned by digest) | workspaces, evidence index, jobs, runs, experiments, audit log |
| `migrate` | `pap-api` | applies the database migrations (Alembic), then exits |
| `api` | `pap-api` | the HTTP API (FastAPI); never commands a device itself |
| `worker` | `pap-api` | evaluation jobs and workflow/experiment runs (durable leases), artifact capture; runs the pinned OpenMHS engine |
| `web` | `pap-web` | the interface (Next.js); signs people in and proxies the API |
| `virtual-lab` | `pap-virtual-lab` | the simulated LabThings laboratory, for trying the product; remove it in production if unused |
| `otel-collector`, `prometheus` | profile `observability` | optional traces and metrics |

Simulation hosts (`runtimes/sim-host`) run next to the simulator they front (for Gazebo: on the machine with the
built workspace) and are offered to workspaces through the environment catalog below.

## Install

```bash
cp .env.example .env        # then edit: see "Configuration"
docker compose up -d --build
docker compose ps           # api and web healthy; migrate exited 0
```

The web app listens on `127.0.0.1:3000` and the API on `127.0.0.1:8000`. Put a TLS-terminating reverse proxy
(nginx, Caddy, Traefik) in front of the web app for anyone else to reach it; the API does not need to be public (the
web app proxies it), except for service credentials used by CI or by the agent tools.

## Configuration

Set in `.env` (never commit it). The essentials for production:

| Setting | Value |
|---|---|
| `PAP_ENV` | `production` (refuses development sign-in) |
| `PAP_DATABASE_URL` | the PostgreSQL URL |
| `PAP_AUTH_MODE` | `oidc` (the default) with `PAP_OIDC_ISSUER`, `PAP_OIDC_AUDIENCE` |
| `PAP_WEB_AUTH` | `oidc` with `PAP_OIDC_CLIENT_ID`, `PAP_WEB_ORIGIN` (public URL), `PAP_SESSION_SECRET` (32+ random characters) |
| `PAP_STORAGE_BACKEND` | `local` (a volume) or `s3` (`PAP_S3_BUCKET`, endpoint for MinIO/SeaweedFS/R2) |
| `PAP_ENVIRONMENTS` | the environment catalog (below) |
| `PAP_METRICS_TOKEN` | a bearer token for `/metrics` in production |
| `OPENMHS_BIN_SHA256` | the pinned engine digest (the worker refuses another engine) |

Any OIDC provider works (Keycloak, Entra ID, Okta, Auth0, Google). Register a public client with redirect URI
`<PAP_WEB_ORIGIN>/auth/callback` and PKCE; access tokens must carry the API audience.

### Environment catalog (what workspaces may connect)

Only the operator decides which environments exist; users choose from this list and never type an endpoint.

```json
[
  {"key": "virtual-lab", "name": "Virtual laboratory", "kind": "simulated", "endpoint": "http://virtual-lab:8100"},
  {"key": "gazebo-openamr", "name": "Gazebo: OpenAMRobot", "kind": "simulated", "endpoint": "http://sim-host:8300"},
  {"key": "line-3", "name": "Line 3 instruments", "kind": "physical", "endpoint": "http://labthings.line3:5000"}
]
```

`kind: physical` environments can be discovered and read; the platform never sends them a command (D-026). A command
goes only to an environment the operator marked `simulated` whose devices also report `simulated=true`.

## Operations

- **Health**: `GET /healthz` (API), the web root; `docker compose ps` shows health.
- **Backups**: `pg_dump` the database daily; back up the artifact volume or bucket. Artifacts are content-addressed
  (`sha256/<xx>/<digest>`), so an incremental copy is safe and a restored file is checked against its digest when read.
- **Upgrades**: pull, `docker compose up -d --build`; `migrate` applies new migrations before `api` and `worker` start.
  Migrations only move forward in production; take a backup first.
- **Scaling**: run more `worker` replicas; runs and jobs are claimed with leases (`FOR UPDATE SKIP LOCKED`), a lost
  worker's run is resumed from its journal. One simulation host runs one scenario at a time by design.
- **Logs** are JSON on stderr; **metrics** at `/metrics`; **traces** over OTLP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.
- **Audit**: every allowed or denied action is recorded with the actor, resource and decision.

## Security checklist

- [ ] `PAP_ENV=production`, `PAP_AUTH_MODE=oidc`, `PAP_WEB_AUTH=oidc`; development sign-in is refused at start.
- [ ] TLS in front of the web app; API and database not exposed publicly.
- [ ] `PAP_SESSION_SECRET`, database and S3 credentials from a secret store, not from a committed file.
- [ ] Workspace roles assigned on purpose (viewer, engineer, admin); service credentials scoped to one workspace and role,
      rotated, revoked when unused.
- [ ] The environment catalog lists physical environments as `physical`.
- [ ] Agent harness keys (`PAP_LLM_*`) only in the environment of the person running it; per-session and per-experiment
      caps set; traces reviewed (they never contain keys).
- [ ] Backups taken and a restore rehearsed.
- [ ] Dependency audits clean (`npm audit`, `pip-audit`, the CI scans).
