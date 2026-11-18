#!/usr/bin/env bash
# Fetch the pinned SeaweedFS release (a real S3-compatible server) for the storage tests (DATA-004), checking the
# SHA-256 that GitHub publishes for the release asset. Test tooling only: never part of the product or its images.
#
#   bash scripts/get-seaweedfs.sh      # -> .tools/seaweedfs/weed(.exe)
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=4.52
case "$(uname -s)-$(uname -m)" in
  MINGW*-x86_64|MSYS*-x86_64|CYGWIN*-x86_64)
    ASSET=windows_amd64.zip; SHA=e3dfe6c441686887b8fdde4420aa2c11ad9c8ce152340bd053e8176e07851a26 ;;
  Linux-x86_64) ASSET=linux_amd64.tar.gz; SHA=8b538c22d47d0c3fb6792adaa6b0c735a967401270a53427d5a476dcaca9b7ae ;;
  Linux-aarch64) ASSET=linux_arm64.tar.gz; SHA=b70a09540bf8aa2b9ea2a48b3b16abe27e162e90a0c3bf041f8d414caf52de8a ;;
  Darwin-arm64) ASSET=darwin_arm64.tar.gz; SHA=7aed4f7db8048a8aedab47a71ea4dd3875caa5abdb925d6aa72fb65438a47910 ;;
  *) echo "no pinned SeaweedFS build for $(uname -s)-$(uname -m)" >&2; exit 2 ;;
esac

DEST=.tools/seaweedfs
mkdir -p "$DEST"
TMPF="$DEST/$ASSET.partial"
curl -sSLf -o "$TMPF" "https://github.com/seaweedfs/seaweedfs/releases/download/$VERSION/$ASSET"
GOT="$(sha256sum "$TMPF" | cut -d' ' -f1)"
if [ "$GOT" != "$SHA" ]; then
  rm -f "$TMPF"
  echo "checksum mismatch for $ASSET: got $GOT, expected $SHA" >&2
  exit 3
fi
case "$ASSET" in
  *.zip) unzip -o -q "$TMPF" -d "$DEST" ;;
  *.tar.gz) tar -xzf "$TMPF" -C "$DEST" ;;
esac
rm -f "$TMPF"
"$DEST"/weed* version
