#!/usr/bin/env bash
# The pre-fix arm of upstream's command-timeout scenario (#79 / PR #177): the same run as run_scenario.sh, with the two
# wiring files the fix changes (gz_bridge.yaml, gz_simulator.launch.py) put back to origin/main for the duration of the
# run, then restored. The workspace is built with --symlink-install, so no rebuild is needed.
#
# This edits the LOCAL checkout temporarily and refuses to start unless it is clean (the fix commit, nothing else), and
# verifies it is clean again afterwards. Nothing is pushed or committed. The run identity says the tree was dirty and
# names the two files, so the recording is never mistaken for a run of a clean commit.
#
#   bash run_main.sh <out-dir>        WS=~/p79
set -u
OUT="${1:?out dir}"
WS="${WS:-$HOME/p79}"; REPO="$WS/src/openamr-platform-sw"; HERE="$(cd "$(dirname "$0")" && pwd)"
G=ros2/src/openamrobot_gazebo
FILES="$G/config/gz_bridge.yaml $G/launch/gz_simulator.launch.py"
cd "$REPO" || exit 2
[ -z "$(git status --porcelain)" ] || { echo "refusing: $REPO has local changes"; exit 2; }
git rev-parse --verify -q origin/main >/dev/null || { echo "refusing: no origin/main"; exit 2; }
BACKUP="$(mktemp -d)"
restore() {
  for f in $FILES; do [ -f "$BACKUP/$(basename "$f")" ] && cp "$BACKUP/$(basename "$f")" "$REPO/$f"; done
  rm -rf "$BACKUP"
  if [ -n "$(git -C "$REPO" status --porcelain)" ]; then echo "WARNING: checkout is not clean after the run"; git -C "$REPO" status --short; else echo "checkout restored: clean"; fi
}
trap restore EXIT
for f in $FILES; do cp "$f" "$BACKUP/$(basename "$f")"; git show "origin/main:$f" > "$f"; done
export PAP_IDENTITY_NOTE="pre-fix arm: gz_bridge.yaml and gz_simulator.launch.py taken from origin/main ($(git rev-parse --short origin/main)) over the fix commit; the new node and its config are installed but not launched"
bash "$HERE/run_scenario.sh" main "$OUT"
