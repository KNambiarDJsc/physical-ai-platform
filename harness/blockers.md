# Blockers, open dependencies and known failures

Each entry: what, impact, what unblocks it, owner. Remove an entry only when it is resolved, and say how in
progress.md.

## B-001 Docker engine not running on the development workstation
Docker Desktop's engine pipe is absent; RAM (~2.6 GB free of 16) is needed by the user. Impact: Compose
stack (INF-003), Keycloak (live OIDC), MinIO-class S3 server and container image scans cannot be run
locally. Unblock: user starts Docker Desktop, or these run in GitHub Actions. Owner: user.

## B-002 No external customer data
All evidence available is open data (CoreSense, CC BY 4.0), simulation (Gazebo, LeRobot PushT) or
synthetic. Impact: no claim about real customer performance is possible. Unblock: a real robotics team's
recording. Owner: user (customer discovery).

## B-003 Graphify project install awaits review
`graphify` 0.9.97 is installed as a uv tool. `graphify claude install --project` writes hooks and skills
into `.claude/`; it has not been run here, pending review of what it installs. Graphify stays optional
and is not needed for any gate. Owner: next session (review), user (approve).

## B-004 Live OIDC provider not exercised
JWT validation is tested with a locally generated RSA key set and JWKS. A real IdP (Keycloak) round trip
needs Docker (B-001). Owner: user/CI.
