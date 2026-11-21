#!/usr/bin/env bash
# Installs the two third-party design skills as project-scoped development tools, pinned to the commits that were
# reviewed (D-025). Skill text only: no installer is run, no hook is registered, no binary is downloaded.
#
#   bash scripts/install-design-skills.sh          # install or refresh into .claude/skills/ (gitignored)
#   bash scripts/install-design-skills.sh --remove
#
# Impeccable (Apache-2.0) is used for UX, accessibility and consistency audits of the application. Its launcher
# (scripts/impeccable) is deliberately not copied: it downloads a native engine on first use, and its installer adds
# hooks that run on every edit outside model approval. Without the launcher the skill takes its documented
# "launcher unavailable" path and reads PRODUCT.md and DESIGN.md directly.
#
# Taste Skill (MIT) targets marketing websites. Use it only for a future public site, never for the application
# (DESIGN.md wins). Invoking it registers its own Stop hook (node scripts/gate.mjs, up to 600 s, needs Chrome).
set -euo pipefail
cd "$(dirname "$0")/.."

IMPECCABLE_REPO=https://github.com/pbakaus/impeccable.git
IMPECCABLE_SHA=b49177d32788f2dc585c42831d845dacf1ebed2c   # 2026-11-18, skill version 4.10.0
TASTE_REPO=https://github.com/Leonxlnx/taste-skill.git
TASTE_SHA=f6b76575f949707b4e3c37cd86cb44b0b98643e8        # 2026-11-07, tasteskill 2.5.1

DEST=.claude/skills
if [ "${1:-}" = "--remove" ]; then
  rm -rf "$DEST/impeccable" "$DEST/design-taste-frontend"
  echo "Removed the design skills."
  exit 0
fi

WORK="$(mktemp -d "${TMPDIR:-${TMP:-/tmp}}/design-skills.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

fetch() { # repo sha dir
  git init -q "$3"
  git -C "$3" remote add origin "$1"
  git -C "$3" fetch -q --depth 1 origin "$2"
  git -C "$3" checkout -q FETCH_HEAD
  [ "$(git -C "$3" rev-parse HEAD)" = "$2" ] || { echo "commit mismatch for $1" >&2; exit 1; }
}

fetch "$IMPECCABLE_REPO" "$IMPECCABLE_SHA" "$WORK/impeccable"
fetch "$TASTE_REPO" "$TASTE_SHA" "$WORK/taste"

mkdir -p "$DEST"
rm -rf "$DEST/impeccable" "$DEST/design-taste-frontend"

# Impeccable: SKILL.md and the reference playbooks only.
mkdir -p "$DEST/impeccable"
cp "$WORK/impeccable/plugin/skills/impeccable/SKILL.md" "$DEST/impeccable/"
cp -r "$WORK/impeccable/plugin/skills/impeccable/reference" "$DEST/impeccable/"
cp "$WORK/impeccable/LICENSE" "$DEST/impeccable/LICENSE"
cp "$WORK/impeccable/NOTICE.md" "$DEST/impeccable/NOTICE.md"

# Taste Skill: the whole skill folder (its checker scripts and assets are part of how it works).
cp -r "$WORK/taste/skills/taste-skill" "$DEST/design-taste-frontend"
cp "$WORK/taste/LICENSE" "$DEST/design-taste-frontend/LICENSE"

printf 'impeccable %s\ndesign-taste-frontend %s\n' "$IMPECCABLE_SHA" "$TASTE_SHA" >"$DEST/.design-skills-pins"
echo "Installed: impeccable@${IMPECCABLE_SHA:0:7} (skill text, no launcher, no hooks), design-taste-frontend@${TASTE_SHA:0:7}"
