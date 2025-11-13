#!/bin/sh
set -euo pipefail

OUT=atp-main-appliance/artifacts/post-verify-$(date -u +%Y%m%dT%H%M%SZ).txt
echo "Starting post-verify" > "$OUT"
for i in 1 2 3 4 5; do
  if curl -fsS http://127.0.0.1:7443/healthz >> "$OUT" 2>&1; then
    echo "health ok" >> "$OUT"
    exit 0
  fi
  sleep 2
done
echo "health check failed" >> "$OUT"
exit 2
