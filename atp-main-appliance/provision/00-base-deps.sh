#!/bin/sh
set -euo pipefail
# Install base packages expected in build image (Debian/Ubuntu)
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl wget gnupg apt-transport-https \
  qemu-utils qemu-system-x86 virtinst jq tar unzip python3 python3-venv python3-pip openssl git

# Create system user for runtime
id -u atp >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/atp -M -s /usr/sbin/nologin atp || true

echo "APPLIANCE: base deps installed"
