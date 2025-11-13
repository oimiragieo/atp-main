#!/bin/sh
set -euo pipefail

PYV=/opt/atp/venv
if [ ! -d "$PYV" ]; then
  python3 -m venv "$PYV"
  "$PYV/bin/pip" install --upgrade pip setuptools
fi

echo "APPLIANCE: python venv ready at $PYV"
