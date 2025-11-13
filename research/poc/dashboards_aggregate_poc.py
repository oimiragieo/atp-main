"""Dashboards aggregate POC.
Combines multiple dashboard JSON fragments (windows, consensus, predictability) into a single
composite structure with validation of required panels.
"""

from __future__ import annotations

from typing import Any

# Minimal synthetic fragments (would be loaded from files in a fuller impl)
WINDOWS = {"title": "Windows", "panels": [{"id": 1, "name": "Window Depth"}]}
CONSENSUS = {"title": "Consensus", "panels": [{"id": 2, "name": "Agreement"}]}
PREDICT = {"title": "Predictability", "panels": [{"id": 3, "name": "MAPE"}]}

REQUIRED = {"Window Depth", "Agreement", "MAPE"}


def aggregate() -> dict[str, Any]:
    composite = {"title": "ATP Composite", "dashboards": [WINDOWS, CONSENSUS, PREDICT]}
    panels = {p["name"] for d in composite["dashboards"] for p in d["panels"]}
    missing = REQUIRED - panels
    assert not missing, f"Missing panels: {missing}"
    return composite


if __name__ == "__main__":
    agg = aggregate()
    assert len(agg["dashboards"]) == 3
    print("OK: dashboards aggregate POC passed; panels=", [p["name"] for d in agg["dashboards"] for p in d["panels"]])
