#!/usr/bin/env bash
# Start the local stack (scripts/dev_stack.py), check it answers, run one real evaluation through the API and check
# the reports; with --e2e also run the Playwright suites (happy path and failure paths) against the same stack.
# The stack is stopped on exit, database included. State goes to var/smoke/ so a running dev stack is not touched.
#
#   bash scripts/smoke.sh            # API smoke
#   bash scripts/smoke.sh --e2e      # plus the browser suites
#
# Env: PAP_SMOKE_API_PORT (8765), PAP_SMOKE_WEB_PORT (3765), PAP_SKIP_WEB_BUILD=1 to reuse apps/web/.next.
set -euo pipefail
cd "$(dirname "$0")/.."

E2E=0
for a in "$@"; do
  case "$a" in
    --e2e) E2E=1 ;;
    *) echo "unknown argument: $a" >&2; exit 2 ;;
  esac
done

API_PORT="${PAP_SMOKE_API_PORT:-8765}"
WEB_PORT="${PAP_SMOKE_WEB_PORT:-3765}"
STATE="var/smoke"
RUN="$STATE/dev-stack"
mkdir -p "$RUN"
READY="$RUN/ready.json"
STOP="$RUN/stop"
LOG="$RUN/stack.log"
rm -f "$READY" "$STOP"
# Keep temporary files with the rest of the smoke state (C: on this machine is often full).
mkdir -p "$STATE/tmp"
TMP="$(cd "$STATE/tmp" && { pwd -W 2>/dev/null || pwd; })"
export TMP TEMP="$TMP" TMPDIR="$TMP"

test -f .engine/build.json || { echo "engine not built: bash scripts/build-openmhs.sh" >&2; exit 1; }
if [ "${PAP_SKIP_WEB_BUILD:-0}" != "1" ] || [ ! -d apps/web/.next ]; then
  echo "== building web app"
  npm --prefix apps/web run build >"$RUN/web-build.log" 2>&1 || { tail -40 "$RUN/web-build.log"; exit 1; }
fi

echo "== starting stack (log: $LOG)"
uv run python scripts/dev_stack.py --api-port "$API_PORT" --web-port "$WEB_PORT" \
  --state-dir "$STATE" --ready-file "$READY" --stop-file "$STOP" >"$LOG" 2>&1 &
STACK=$!

stop_stack() {
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

echo "== API smoke"
uv run python scripts/smoke_api.py --api "http://127.0.0.1:$API_PORT"

if [ "$E2E" = 1 ]; then
  echo "== browser suites"
  PAP_WEB_URL="http://127.0.0.1:$WEB_PORT" PAP_WORKER_PID_FILE="$(pwd)/$RUN/worker.pid" \
    npm --prefix apps/web run e2e
fi
echo "== smoke passed"
