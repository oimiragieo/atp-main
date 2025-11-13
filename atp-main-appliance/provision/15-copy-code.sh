#!/bin/sh
set -euo pipefail
# Usage: 15-copy-code.sh <version> <repo-tarball>
VER=${1:-devlocal}
REPO_TGZ=${2:-/tmp/repo.tgz}

if [ ! -f "$REPO_TGZ" ]; then
  echo "Repo tarball $REPO_TGZ not found; aborting" >&2
  exit 2
fi

STG=/opt/atp/releases/$VER
mkdir -p "$STG"
tar -xzf "$REPO_TGZ" -C /tmp
REPO_DIR=$(tar -tzf "$REPO_TGZ" | head -1 | cut -f1 -d"/")
cp -a /tmp/$REPO_DIR/router_service "$STG/"
cp -a /tmp/$REPO_DIR/services/memory-gateway "$STG/" || true
cp -a /tmp/$REPO_DIR/ui/admin-aggregator "$STG/" || true

echo "APPLIANCE: copied repo to $STG"
