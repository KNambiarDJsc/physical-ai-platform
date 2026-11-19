#!/usr/bin/env bash
# Self-hosted trial installation: one command, no accounts, no credentials of ours.
#
#   bash trial/start.sh            # build (first time only) and start everything
#   bash trial/start.sh stop       # stop; your data stays
#   bash trial/start.sh reset      # stop and DELETE all trial data (database, uploaded files)
#   bash trial/start.sh status
#
# Needs: Docker with the Compose plugin (v2.20+), git, and about 8 minutes the first time (the engine is compiled
# from source inside the image build). Works in Git Bash or WSL on Windows, and in any POSIX shell.
#
# What it starts: PostgreSQL, the API, the evaluation worker (with the pinned OpenMHS engine), and the web app, on
# http://127.0.0.1:3000 only (not reachable from other machines). It uses the labelled DEVELOPMENT identity: you
# type any name to sign in. That is fine for one person on one machine and is NOT how a shared installation runs.
# The database password is generated on your machine and kept in trial/.state/ (not in git).
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT=pap-trial
WEB_PORT="${PAP_WEB_PORT:-3000}"
API_PORT="${PAP_API_PORT:-8000}"
STATE=trial/.state
CMD="${1:-start}"

command -v docker >/dev/null || { echo "Docker is not installed or not on PATH." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "The Docker Compose plugin is missing (need 'docker compose')." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "The Docker engine is not running. Start Docker Desktop (or the docker service) first." >&2; exit 1; }

mkdir -p "$STATE"
if [ ! -s "$STATE/db-password" ]; then
  # The database volume keeps the password it was created with, so the password is generated once and reused.
  (umask 077; LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32 >"$STATE/db-password")
fi
PAP_DB_PASSWORD="$(cat "$STATE/db-password")"
export PAP_DB_PASSWORD PAP_WEB_PORT="$WEB_PORT" PAP_API_PORT="$API_PORT" PAP_ENV=development PAP_AUTH_MODE=dev
dc() { docker compose -p "$PROJECT" "$@"; }

case "$CMD" in
  start)
    for port in "$WEB_PORT" "$API_PORT"; do
      if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
        echo "Port $port is already in use. Free it, or run: PAP_WEB_PORT=3100 PAP_API_PORT=8100 bash trial/start.sh" >&2
        exit 1
      fi
    done
    echo "Building and starting (first time: about 8 minutes, mostly compiling the engine)..."
    dc up -d --build --wait --wait-timeout 900
    echo
    echo "Ready:  http://127.0.0.1:$WEB_PORT"
    echo "Sign in with any name on the Settings page (development identity, this machine only)."
    echo "Next:   open trial/EXERCISE.md"
    ;;
  stop)
    dc stop
    echo "Stopped. Data kept. Start again with: bash trial/start.sh"
    ;;
  status)
    dc ps
    ;;
  reset)
    dc down -v --remove-orphans
    rm -rf "$STATE"
    echo "All trial data deleted."
    ;;
  *)
    echo "usage: bash trial/start.sh [start|stop|status|reset]" >&2
    exit 2
    ;;
esac
