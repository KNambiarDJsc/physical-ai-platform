#!/usr/bin/env bash
# Start the platform, check it answers, run one real evaluation through the API and check the reports; with --e2e
# also run the Playwright suites (happy path and failure paths) against the same stack. The stack is stopped on
# exit, database included.
#
#   bash scripts/smoke.sh                  # local stack (scripts/dev_stack.py, no Docker), state in var/smoke/
#   bash scripts/smoke.sh --e2e            # plus the browser suites
#   bash scripts/smoke.sh --compose        # Docker Compose stack instead (builds the images; INF-003, SEC-001)
#   bash scripts/smoke.sh --compose --e2e
#   bash scripts/smoke.sh --compose --observability   # plus the OTel Collector and Prometheus profile (OBS-002)
#   bash scripts/smoke.sh --oidc           # local stack signing in through a real OIDC provider (AUTH-002)
#   bash scripts/smoke.sh --compose --trial  # plus the trial exercise (trial/EXERCISE.md) done through the UI
#
# --compose also checks that every service runs as a non-root user, that the worker has its CPU, memory, process
# and read-only limits, and that the web image reaches the API through its runtime proxy.
#
# Env: PAP_SMOKE_API_PORT (8765), PAP_SMOKE_WEB_PORT (3765), PAP_SKIP_WEB_BUILD=1 to reuse apps/web/.next.
set -euo pipefail
cd "$(dirname "$0")/.."

E2E=0
TRIAL=0
COMPOSE=0
OIDC=0
OBS=0
for a in "$@"; do
  case "$a" in
    --e2e) E2E=1 ;;
    --trial) TRIAL=1 ;;
    --compose) COMPOSE=1 ;;
    --oidc) OIDC=1 ;;
    --observability) OBS=1 ;;
    *) echo "unknown argument: $a" >&2; exit 2 ;;
  esac
done

API_PORT="${PAP_SMOKE_API_PORT:-8765}"
WEB_PORT="${PAP_SMOKE_WEB_PORT:-3765}"
STATE="var/smoke"
RUN="$STATE/dev-stack"
mkdir -p "$RUN" "$STATE/tmp"
# Keep temporary files with the rest of the smoke state (C: on the development machine is often full).
TMP="$(cd "$STATE/tmp" && { pwd -W 2>/dev/null || pwd; })"
export TMP TEMP="$TMP" TMPDIR="$TMP"

if [ "$COMPOSE" = 1 ]; then
  PROJECT=pap-smoke
  export PAP_DB_PASSWORD="${PAP_DB_PASSWORD:-smoke-$RANDOM$RANDOM}"
  export PAP_API_PORT="$API_PORT" PAP_WEB_PORT="$WEB_PORT" PAP_WORKER_LEASE_S="${PAP_WORKER_LEASE_S:-10}"
  export PAP_LAB_PORT="${PAP_SMOKE_LAB_PORT:-8865}"
  if [ "$OBS" = 1 ]; then
    export COMPOSE_PROFILES=observability PAP_PROM_PORT="${PAP_SMOKE_PROM_PORT:-9765}"
    export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
  fi
  dc() { docker compose -p "$PROJECT" "$@"; }
  trap 'dc logs --no-color >"$RUN/compose.log" 2>&1 || true; dc down -v --remove-orphans >/dev/null 2>&1 || true' EXIT
  echo "== building and starting the Compose stack"
  dc up -d --build --wait --wait-timeout 600

  echo "== container checks"
  for s in api worker web virtual-lab; do
    uid="$(dc exec -T "$s" id -u | tr -d '\r')"
    [ "$uid" != 0 ] || { echo "FAIL $s runs as root" >&2; exit 1; }
    echo "ok   $s runs as uid $uid"
  done
  wid="$(dc ps -q worker)"
  read -r mem cpus pids ro <<<"$(docker inspect -f '{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}} {{.HostConfig.PidsLimit}} {{.HostConfig.ReadonlyRootfs}}' "$wid")"
  [ "$mem" -gt 0 ] && [ "$cpus" -gt 0 ] && [ "$pids" -gt 0 ] && [ "$ro" = true ] \
    || { echo "FAIL worker limits: memory=$mem nanocpus=$cpus pids=$pids read_only=$ro" >&2; exit 1; }
  echo "ok   worker limits: memory=$mem nanocpus=$cpus pids=$pids read_only=$ro"
  engine="$(dc exec -T api python -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthz'))['engine'])")"
  echo "ok   engine in the image: $engine"
  code="$(curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer dev:smoke-proxy' "http://127.0.0.1:$WEB_PORT/api/v1/me")"
  [ "$code" = 200 ] || { echo "FAIL web proxy to API returned $code" >&2; exit 1; }
  echo "ok   web reaches the API through its runtime proxy"

  echo "== API smoke"
  uv run python scripts/smoke_api.py --api "http://127.0.0.1:$API_PORT"
  if [ "$OBS" = 1 ]; then
    echo "== observability: the collector receives traces and Prometheus scrapes the API and the worker"
    uv run python scripts/check_observability.py --prometheus "http://127.0.0.1:$PAP_PROM_PORT" \
      --collector-logs "docker compose -p $PROJECT logs --no-color otel-collector" \
      || { dc logs --no-color otel-collector 2>&1 | tail -30 >&2; exit 1; }
  fi
  if [ "$E2E" = 1 ]; then
    echo "== browser suites"
    # Kill the worker's main process from the host (as a crash would); the restart policy starts it again.
    kill_cmd="sudo kill -9 \$(docker inspect -f '{{.State.Pid}}' \$(docker compose -p $PROJECT ps -q worker))"
    PAP_WEB_URL="http://127.0.0.1:$WEB_PORT" PAP_LAB_URL="http://127.0.0.1:$PAP_LAB_PORT" PAP_WORKER_KILL_CMD="$kill_cmd" \
      npm --prefix apps/web run e2e
  fi
  if [ "$TRIAL" = 1 ]; then
    echo "== trial exercise dry run (trial/EXERCISE.md, through the UI)"
    PAP_WEB_URL="http://127.0.0.1:$WEB_PORT" PAP_E2E_TRIAL=1 npm --prefix apps/web run e2e -- e2e/trial-exercise.spec.ts
  fi
  echo "== smoke passed (compose)"
  exit 0
fi

READY="$RUN/ready.json"
STOP="$RUN/stop"
LOG="$RUN/stack.log"
rm -f "$READY" "$STOP"

test -f .engine/build.json || { echo "engine not built: bash scripts/build-openmhs.sh" >&2; exit 1; }
if [ "${PAP_SKIP_WEB_BUILD:-0}" != "1" ] || [ ! -d apps/web/.next ]; then
  echo "== building web app"
  npm --prefix apps/web run build >"$RUN/web-build.log" 2>&1 || { tail -40 "$RUN/web-build.log"; exit 1; }
fi

if [ "$OIDC" = 1 ]; then
  OIDC_PORT="${PAP_SMOKE_OIDC_PORT:-9411}"
  OIDC_STOP="$RUN/oidc-stop"
  AUDIENCE="https://api.pap.test"
  rm -f "$OIDC_STOP"
  echo "== starting the test OIDC provider on :$OIDC_PORT"
  (cd apps/web && node e2e/support/oidc-provider.mjs --port "$OIDC_PORT" --web-origin "http://127.0.0.1:$WEB_PORT"     --audience "$AUDIENCE" --stop-file "../../$OIDC_STOP") >"$RUN/oidc.log" 2>&1 &
  for _ in $(seq 1 60); do
    curl -sf "http://127.0.0.1:$OIDC_PORT/.well-known/openid-configuration" >/dev/null && break
    sleep 0.5
  done
  curl -sf "http://127.0.0.1:$OIDC_PORT/.well-known/openid-configuration" >/dev/null     || { echo "OIDC provider did not start" >&2; cat "$RUN/oidc.log" >&2; exit 1; }
  export PAP_AUTH_MODE=oidc PAP_OIDC_ISSUER="http://127.0.0.1:$OIDC_PORT" PAP_OIDC_AUDIENCE="$AUDIENCE"
  export PAP_WEB_AUTH=oidc PAP_OIDC_CLIENT_ID=pap-web PAP_OIDC_RESOURCE="$AUDIENCE" PAP_OIDC_SCOPE="openid profile api"
  export PAP_WEB_ORIGIN="http://127.0.0.1:$WEB_PORT"
  PAP_SESSION_SECRET="$(uv run python -c 'import secrets; print(secrets.token_urlsafe(48))')"
  export PAP_SESSION_SECRET
fi

echo "== starting stack (log: $LOG)"
uv run python scripts/dev_stack.py --api-port "$API_PORT" --web-port "$WEB_PORT" \
  --lab-port "${PAP_SMOKE_LAB_PORT:-8865}" --ros-replay runtimes/ros-observer/tests/fixtures/openamr-upperbody-mock.snapshot.json \
  --ros-replay-port "${PAP_SMOKE_ROS_PORT:-8866}" ${PAP_SMOKE_ROS_OBSERVER:+--ros-observer "$PAP_SMOKE_ROS_OBSERVER"} \
  --state-dir "$STATE" --ready-file "$READY" --stop-file "$STOP" >"$LOG" 2>&1 &
STACK=$!

stop_stack() {
  [ "$OIDC" = 1 ] && touch "$OIDC_STOP"
  touch "$STOP"
  for _ in $(seq 1 60); do
    kill -0 "$STACK" 2>/dev/null || return 0
    sleep 0.5
  done
  echo "stack did not stop within 30 s; see $LOG" >&2
}
trap stop_stack EXIT

for _ in $(seq 1 360); do
  [ -f "$READY" ] && break
  kill -0 "$STACK" 2>/dev/null || { echo "stack exited during start-up:" >&2; tail -40 "$LOG" >&2; exit 1; }
  sleep 0.5
done
[ -f "$READY" ] || { echo "stack not ready after 180 s" >&2; tail -40 "$LOG" >&2; exit 1; }
cat "$READY"; echo

if [ "$OIDC" = 1 ]; then
  echo "== sign-in through the OIDC provider (browser)"
  PAP_WEB_URL="http://127.0.0.1:$WEB_PORT" PAP_E2E_OIDC=1 PAP_E2E_OIDC_ISSUER="$PAP_OIDC_ISSUER"     npm --prefix apps/web run e2e -- e2e/oidc.spec.ts
  echo "== smoke passed (oidc)"
  exit 0
fi

echo "== API smoke"
uv run python scripts/smoke_api.py --api "http://127.0.0.1:$API_PORT"

if [ "$E2E" = 1 ]; then
  echo "== browser suites"
  PAP_WEB_URL="http://127.0.0.1:$WEB_PORT" PAP_WORKER_PID_FILE="$(pwd)/$RUN/worker.pid" \
    npm --prefix apps/web run e2e
fi
if [ "$TRIAL" = 1 ]; then
  echo "== trial exercise dry run (trial/EXERCISE.md, through the UI)"
  PAP_WEB_URL="http://127.0.0.1:$WEB_PORT" PAP_E2E_TRIAL=1 npm --prefix apps/web run e2e -- e2e/trial-exercise.spec.ts
fi
echo "== smoke passed"
