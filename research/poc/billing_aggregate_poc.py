"""Billing/usage analytics aggregate POC.
Combines accountant report with computed ARPU and adapter utilization ratios.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.cost_accounting_poc import Accountant, Event


class BillingAggregate:
    def __init__(self):
        self.accountant = Accountant()

    def record(self, tenant: str, adapter: str, in_t: int, out_t: int, usd: int):
        self.accountant.record(Event(tenant, adapter, in_t, out_t, usd))

    def summarize(self):
        rep = self.accountant.report()
        tenants = rep["tenants"]
        adapters = rep["adapters"]
        total_usd = sum(t["usd_micros"] for t in tenants.values()) or 1
        arpu = {tenant: t["usd_micros"] for tenant, t in tenants.items()}
        utilization = {ad: a["usd_micros"] / total_usd for ad, a in adapters.items()}
        return {
            "arpu": arpu,
            "utilization": utilization,
            "total_usd_micros": total_usd,
        }


if __name__ == "__main__":
    b = BillingAggregate()
    b.record("t1", "A", 100, 40, 50000)
    b.record("t2", "A", 50, 20, 30000)
    b.record("t1", "B", 200, 80, 90000)
    s = b.summarize()
    assert s["total_usd_micros"] == 170000
    assert "A" in s["utilization"] and abs(sum(s["utilization"].values()) - 1.0) < 1e-6
    print("OK: billing aggregate POC passed; summary=", s)
