#!/usr/bin/env bash
# The single verification entry point.
#
#   scripts/verify.sh            full gate: everything below, engine tests required (no skips)
#   scripts/verify.sh --quick    registry, lint, types, unit tests (engine tests run if the engine is built)
#   scripts/verify.sh --python   Python gates only (full)
#   scripts/verify.sh --web      web gates only
#
# A gate whose code does not exist yet is reported as "not present", never as passed.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export UV_CACHE_DIR="${UV_CACHE_DIR:-D:/uv-cache}"

MODE="full"
case "${1:-}" in
  --quick) MODE="quick" ;;
  --python) MODE="python" ;;
  --web) MODE="web" ;;
  "") ;;
  *) echo "usage: $0 [--quick|--python|--web]" >&2; exit 2 ;;
esac

FAILED=()
step() {
  local name="$1"; shift
  printf '\n=== %s\n' "$name"
  if "$@"; then echo "--- ok: $name"; else echo "--- FAILED: $name"; FAILED+=("$name"); fi
}
absent() { printf '\n=== %s\n--- not present yet\n' "$1"; }

python_gates() {
  step "ruff check" uv run ruff check .
  step "ruff format" uv run ruff format --check .
  step "mypy (bridge)" uv run mypy packages/openmhs-bridge/src
  if [ -d services/api/app ] && [ -n "$(ls services/api/app/*.py 2>/dev/null | grep -v __init__)" ]; then
    step "mypy (api)" uv run mypy services/api/app
  else
    absent "mypy (api)"
  fi
  step "contract schemas up to date" bash -c "cd services/api && uv run python -m app.contracts.export --check"
  step "openapi document up to date" uv run python scripts/export_openapi.py --check
  step "demo dataset reproducible" uv run python examples/manipulation-demo/generate.py --check
  if [ "$MODE" = "quick" ]; then
    step "pytest" uv run pytest -q
  else
    step "pytest (engine required)" env PAP_REQUIRE_ENGINE=1 uv run pytest -q
    step "openmhs audit" uv run python scripts/audit_openmhs.py
  fi
}

web_gates() {
  if [ -f apps/web/package.json ]; then
    step "web typecheck" npm --prefix apps/web run -s typecheck
    step "web lint" npm --prefix apps/web run -s lint -- --max-warnings 0
    step "web unit" npm --prefix apps/web run -s test
    step "web api client up to date" npm --prefix apps/web run -s check:api
    if [ "$MODE" != "quick" ]; then step "web build" env NEXT_TELEMETRY_DISABLED=1 npm --prefix apps/web run -s build; fi
  else
    absent "web"
  fi
}

step "feature registry" python scripts/check_features.py
step "no secrets in tracked files" python scripts/check_secrets.py
case "$MODE" in
  quick|full) python_gates; web_gates ;;
  python) python_gates ;;
  web) web_gates ;;
esac

echo
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "verify ($MODE): FAILED: ${FAILED[*]}"
  exit 1
fi
echo "verify ($MODE): all gates passed"
