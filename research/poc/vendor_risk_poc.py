"""Vendor Risk Management POC
Creates a vendor inventory with attributes (sla, security_score, data_sensitivity, last_audit_days),
computes a composite risk score, flags remediation priorities, and outputs summary.
"""

import json
import statistics
from dataclasses import dataclass


@dataclass
class Vendor:
    name: str
    sla_uptime: float  # 0..1
    security_score: int  # 0..100
    data_sensitivity: int  # 1..5
    last_audit_days: int

    def risk(self):
        # Higher risk if low SLA, low security score, high data sensitivity, long since audit
        return (
            (1 - self.sla_uptime) * 0.3
            + (1 - self.security_score / 100) * 0.3
            + (self.data_sensitivity / 5) * 0.2
            + min(self.last_audit_days / 365, 1) * 0.2
        )


def evaluate_vendors(vendors):
    scores = [(v.name, round(v.risk(), 4)) for v in vendors]
    avg = round(statistics.mean(r for _, r in scores), 4)
    high = [n for n, r in scores if r > avg * 1.2]
    return {"scores": scores, "avg": avg, "high_risk": high}


if __name__ == "__main__":
    vendors = [
        Vendor("vector-db", 0.995, 82, 4, 190),
        Vendor("auth-idp", 0.999, 90, 3, 40),
        Vendor("logging-saas", 0.98, 75, 2, 400),
        Vendor("billing-saas", 0.997, 88, 3, 120),
    ]
    res = evaluate_vendors(vendors)
    if res["high_risk"]:
        print("OK: vendor risk POC passed high_risk=" + ",".join(res["high_risk"]))
    else:
        print("FAIL: vendor risk POC no high risk detection", json.dumps(res))
