#!/usr/bin/env bash
# OUR dry run of the trial: install exactly as the README says, do the exercise as written, then clean up.
# Not an external user's result, and not human timing: the UI part is driven by a script (Playwright), so its
# durations are lower bounds on what a person needs. Results go to var/trial-dry-run/.
#
#   bash trial/dry_run.sh        # needs Docker, Node 22 (for the UI driver only) and Python 3.10+
set -euo pipefail
cd "$(dirname "$0")/.."

OUT=var/trial-dry-run
rm -rf "$OUT"
mkdir -p "$OUT"
clock() { date +%s; }

echo "== installing with: bash trial/start.sh"
T0=$(clock)
bash trial/start.sh 2>&1 | tee "$OUT/install.log"
T1=$(clock)
echo "install_seconds=$((T1 - T0))" | tee "$OUT/timings.txt"

cleanup() { bash trial/start.sh reset >"$OUT/reset.log" 2>&1 || true; }
trap cleanup EXIT

echo "== Part A through the web UI (the driver stands in for the engineer; no extra steps)"
npm --prefix apps/web ci --no-audit --no-fund >/dev/null
npx --prefix apps/web playwright install --with-deps chromium >/dev/null
PAP_WEB_URL=http://127.0.0.1:3000 PAP_E2E_TRIAL=1 PAP_TRIAL_OUT="$PWD/$OUT" \
  npm --prefix apps/web run e2e -- e2e/trial-exercise.spec.ts 2>&1 | tee "$OUT/part-a.log"

echo "== Part B with the plain script"
: >"$OUT/part-b.txt"
for args in "mujoco A D" "mujoco A C" "coresense no_failure panel_failure"; do
  python3 trial/time_part_b.py "$OUT" $args | tee -a "$OUT/timings.txt"
done
cat "$OUT/part-b.txt"
echo "== dry run finished"
