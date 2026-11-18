#!/usr/bin/env bash
# Bounded, opt-in engineering loop: each iteration is a fresh non-interactive Claude Code session that follows
# the engineering-loop skill on ONE eligible feature, then this script verifies and decides whether to go on.
#
#   PAP_LOOP=1 scripts/loop.sh [--iterations N] [--minutes M] [--budget-usd X] [--feature ID] [--dry-run]
#
# Stops when: the target feature (or every eligible one) is verified; the agent signals blocked / needs-human;
# two consecutive iterations make no measurable progress; iterations, minutes or budget run out; harness/STOP exists.
# Never bypasses permissions: the session runs in acceptEdits mode under .claude/settings.json; anything else
# that needs approval is denied and the agent must record it as a blocker. Never pushes or deploys.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ITERATIONS=1
MINUTES=60
BUDGET=5
FEATURE=""
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --iterations) ITERATIONS="$2"; shift 2 ;;
    --minutes) MINUTES="$2"; shift 2 ;;
    --budget-usd) BUDGET="$2"; shift 2 ;;
    --feature) FEATURE="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ "${PAP_LOOP:-0}" != "1" ]; then
  echo "the loop is opt-in: set PAP_LOOP=1 (and verify the manual loop first; see CLAUDE.md)" >&2
  exit 2
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "working tree is not clean; commit or stash first so each iteration's change is measurable" >&2
  exit 2
fi

mkdir -p harness/logs
DEADLINE=$(( $(date +%s) + MINUTES * 60 ))
STALL=0

state() { python - <<'PY'
import hashlib, json, subprocess
reg = json.load(open("harness/features.json", encoding="utf-8"))
st = {f["id"]: f["status"] for f in reg["features"]}
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
print(hashlib.sha256(json.dumps([st, head], sort_keys=True).encode()).hexdigest())
PY
}

for i in $(seq 1 "$ITERATIONS"); do
  [ -f harness/STOP ] && { echo "harness/STOP present: stopping"; break; }
  [ "$(date +%s)" -ge "$DEADLINE" ] && { echo "time budget exhausted"; break; }

  TARGET="$FEATURE"
  if [ -z "$TARGET" ]; then
    TARGET="$(python scripts/check_features.py --next | tail -1)"
    case "$TARGET" in features:*|eligible*) TARGET="" ;; esac
  fi
  if [ -z "$TARGET" ]; then echo "no eligible feature"; break; fi
  STATUS="$(python -c "import json,sys;print({f['id']:f['status'] for f in json.load(open('harness/features.json'))['features']}['$TARGET'])")"
  if [ "$STATUS" = "verified" ]; then echo "$TARGET is verified: done"; break; fi

  LOG="harness/logs/loop-$(date +%Y%m%d-%H%M%S)-$i.log"
  BEFORE="$(state)"
  rm -f harness/loop-signal
  PROMPT="Run the engineering-loop skill (.claude/skills/engineering-loop/SKILL.md) for feature $TARGET only. \
Follow CLAUDE.md. When you stop, write exactly one word to harness/loop-signal: progress, verified, blocked or \
needs-human, and make a local commit of your work. Do not push."
  echo "iteration $i: $TARGET -> $LOG"
  if [ "$DRY" = "1" ]; then echo "dry run: claude -p <prompt> --permission-mode acceptEdits --max-budget-usd $BUDGET"; break; fi

  timeout "$(( DEADLINE - $(date +%s) ))" claude -p "$PROMPT" --permission-mode acceptEdits \
    --max-budget-usd "$BUDGET" --no-session-persistence > "$LOG" 2>&1 || echo "session exited non-zero (see $LOG)"

  SIGNAL="$(cat harness/loop-signal 2>/dev/null || echo none)"
  bash scripts/verify.sh --quick >> "$LOG" 2>&1 && VERIFY=ok || VERIFY=failed
  AFTER="$(state)"
  echo "iteration $i: signal=$SIGNAL verify=$VERIFY changed=$([ "$BEFORE" != "$AFTER" ] && echo yes || echo no)"

  case "$SIGNAL" in
    blocked|needs-human) echo "stopping: agent signalled $SIGNAL (see harness/blockers.md)"; break ;;
  esac
  if [ "$VERIFY" = "failed" ]; then echo "stopping: verify.sh --quick failed after iteration $i"; break; fi
  if [ "$BEFORE" = "$AFTER" ]; then STALL=$((STALL + 1)); else STALL=0; fi
  if [ "$STALL" -ge 2 ]; then echo "stopping: two iterations without measurable progress"; break; fi
done
