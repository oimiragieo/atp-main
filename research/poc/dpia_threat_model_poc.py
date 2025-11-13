"""DPIA / Threat modeling POC.
Generates a simple risk register from component + data flow definitions applying STRIDE-like heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Component:
    name: str
    stores_pii: bool
    external: bool
    processes_payments: bool = False


@dataclass
class DataFlow:
    source: str
    target: str
    contains_pii: bool


THREATS = {
    "Spoofing": lambda c: c.external,
    "Tampering": lambda c: c.stores_pii,
    "Repudiation": lambda c: c.external and c.stores_pii,
    "InformationDisclosure": lambda c: c.stores_pii,
    "DenialOfService": lambda c: True,
    "ElevationOfPrivilege": lambda c: c.external and c.processes_payments,
}


def assess(components: list[Component], flows: list[DataFlow]) -> list[dict]:
    register: list[dict] = []
    comp_index = {c.name: c for c in components}
    for c in components:
        for threat, pred in THREATS.items():
            if pred(c):
                register.append(
                    {
                        "component": c.name,
                        "threat": threat,
                        "risk": "H"
                        if threat in ("InformationDisclosure", "ElevationOfPrivilege") and c.stores_pii
                        else "M",
                    }
                )
    # flow-based risks
    for f in flows:
        if f.contains_pii and (comp_index[f.source].external or comp_index[f.target].external):
            register.append({"component": f.source + "->" + f.target, "threat": "PIIBoundaryLeak", "risk": "H"})
    return register


if __name__ == "__main__":
    comps = [Component("gateway", stores_pii=True, external=True), Component("db", stores_pii=True, external=False)]
    flows = [DataFlow("gateway", "db", contains_pii=True)]
    reg = assess(comps, flows)
    assert any(r["threat"] == "PIIBoundaryLeak" for r in reg)
    print("OK: dpia/threat modeling POC passed; entries=", len(reg))
