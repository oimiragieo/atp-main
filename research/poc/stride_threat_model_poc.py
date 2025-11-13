"""POC: STRIDE threat modeling automation (GAP-050).

Generates a simple STRIDE matrix from an architecture YAML.
"""

from __future__ import annotations

import sys
from typing import Any

STRIDE = [
    "Spoofing",
    "Tampering",
    "Repudiation",
    "Information Disclosure",
    "Denial of Service",
    "Elevation of Privilege",
]


def load_yaml(path: str) -> dict[str, Any]:
    import yaml  # type: ignore

    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def analyze(arch: dict[str, Any]) -> dict[str, dict[str, bool]]:
    comps = arch.get("components", [])
    flows = arch.get("dataflows", [])
    # Initialize matrix
    matrix: dict[str, dict[str, bool]] = {c["name"]: dict.fromkeys(STRIDE, False) for c in comps}
    comp_map = {c["name"]: c for c in comps}
    # Component-based heuristics
    for name, c in comp_map.items():
        t = (c.get("type") or "").lower()
        if t in {"service", "router", "gateway"} and (c.get("exposed") or c.get("port") in (80, 443, 7443)):
            matrix[name]["Spoofing"] = True
            matrix[name]["Tampering"] = True
            matrix[name]["Denial of Service"] = True
        if c.get("stores_data"):
            matrix[name]["Information Disclosure"] = True
            matrix[name]["Tampering"] = True
        if not c.get("has_auth", True):
            matrix[name]["Spoofing"] = True
        if c.get("admin"):
            matrix[name]["Elevation of Privilege"] = True
    # Dataflow-based heuristics
    for f in flows:
        src = f.get("from")
        dst = f.get("to")
        # Crossing external boundary
        if src == "internet" and dst in matrix:
            matrix[dst]["Spoofing"] = True
            matrix[dst]["Tampering"] = True
            matrix[dst]["Information Disclosure"] = True
            matrix[dst]["Denial of Service"] = True
        # Internal flows: mark repudiation risk if no auth
        if src in matrix and dst in matrix:
            if not comp_map[dst].get("has_auth", True):
                matrix[dst]["Repudiation"] = True
    return matrix


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else "data/threat_model_poc.yaml"
    arch = load_yaml(path)
    matrix = analyze(arch)
    # Print a simple table
    for comp, m in matrix.items():
        flags = ", ".join(k for k, v in m.items() if v) or "None"
        print(f"{comp}: {flags}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
