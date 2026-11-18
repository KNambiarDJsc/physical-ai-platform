#!/usr/bin/env bash
# Build the OpenMHS engine binary at the commit pinned in engine.lock.json.
#
# The engine source is never modified: the pinned commit is exported with `git archive` from an existing
# clone (OPENMHS_SRC_REPO) into .engine/src-<commit>, and built there with its own target directory.
# The resulting binary's SHA-256 is recorded in .engine/build.json; the bridge refuses any binary whose
# digest does not match the one the worker was configured with.
#
# Usage: OPENMHS_SRC_REPO=/path/to/Open-MHS scripts/build-openmhs.sh [--jobs N]
# Environment:
#   OPENMHS_SRC_REPO   a clone of the OpenMHS repository that contains the pinned commit (required)
#   ENGINE_DIR         where sources, target dir and the binary go (default: <repo>/.engine)
#   CARGO_OFFLINE      set to 1 to build without network access (crates must already be cached)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOBS=2
while [ $# -gt 0 ]; do
  case "$1" in
    --jobs) JOBS="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

: "${OPENMHS_SRC_REPO:?set OPENMHS_SRC_REPO to a local clone of the OpenMHS repository}"
ENGINE_DIR="${ENGINE_DIR:-$ROOT/.engine}"

lock_field() {
  python -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$ROOT/engine.lock.json" "$1"
}
COMMIT="$(lock_field commit)"
PACKAGE="$(lock_field cargo_package)"
BINARY="$(lock_field binary)"

if ! git -C "$OPENMHS_SRC_REPO" cat-file -e "${COMMIT}^{commit}" 2>/dev/null; then
  echo "commit $COMMIT is not in $OPENMHS_SRC_REPO; fetch it there first (this script does not fetch)" >&2
  exit 3
fi

SRC="$ENGINE_DIR/src-$COMMIT"
if [ ! -f "$SRC/Cargo.lock" ]; then
  rm -rf "$SRC.partial"
  mkdir -p "$SRC.partial"
  git -C "$OPENMHS_SRC_REPO" archive --format=tar "$COMMIT" | tar -x -C "$SRC.partial"
  mv "$SRC.partial" "$SRC"
fi

export CARGO_TARGET_DIR="$ENGINE_DIR/target"
OFFLINE=()
if [ "${CARGO_OFFLINE:-0}" = "1" ]; then OFFLINE=(--offline); fi
(cd "$SRC" && cargo build --release --locked "${OFFLINE[@]}" -p "$PACKAGE" -j "$JOBS")

EXE=""
for candidate in "$CARGO_TARGET_DIR/release/$BINARY" "$CARGO_TARGET_DIR/release/$BINARY.exe"; do
  if [ -f "$candidate" ]; then EXE="$candidate"; fi
done
[ -n "$EXE" ] || { echo "build finished but no $BINARY binary was found" >&2; exit 4; }

mkdir -p "$ENGINE_DIR/bin"
DEST="$ENGINE_DIR/bin/$(basename "$EXE")"
cp "$EXE" "$DEST"
python - "$DEST" "$COMMIT" "$ENGINE_DIR/build.json" <<'PY'
import hashlib, json, platform, subprocess, sys
dest, commit, out = sys.argv[1:4]
digest = hashlib.sha256(open(dest, "rb").read()).hexdigest()
version = subprocess.run([dest, "--version"], capture_output=True, text=True, check=True).stdout.strip()
info = {"binary": dest, "sha256": f"sha256:{digest}", "commit": commit, "version": version,
        "platform": f"{platform.system().lower()}-{platform.machine().lower()}"}
json.dump(info, open(out, "w"), indent=2)
print(json.dumps(info, indent=2))
PY
echo "set OPENMHS_BIN=$DEST and OPENMHS_BIN_SHA256 from $ENGINE_DIR/build.json"
