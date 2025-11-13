"""Cost & token accounting aggregate POC.
Orchestrates per-tenant + per-adapter cost/token rollups using existing Accountant logic,
producing a composite summary suitable for export.
"""

from __future__ import annotations

import os
import sys
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.cost_accounting_poc import Accountant, Event


class AggregateAccountant:
    def __init__(self):
        self.accountant = Accountant()

    def ingest(self, tenant: str, adapter: str, in_tokens: int, out_tokens: int, usd_micros: int):
        self.accountant.record(Event(tenant, adapter, in_tokens, out_tokens, usd_micros))

    def summary(self) -> dict[str, Any]:
        rep = self.accountant.report()
        total_in = sum(v["in_tokens"] for v in rep["tenants"].values())
        total_out = sum(v["out_tokens"] for v in rep["tenants"].values())
        total_usd = sum(v["usd_micros"] for v in rep["tenants"].values())
        rep["totals"] = {"in_tokens": total_in, "out_tokens": total_out, "usd_micros": total_usd}
        return rep


if __name__ == "__main__":
    agg = AggregateAccountant()
    agg.ingest("t1", "A", 100, 40, 50000)
    agg.ingest("t1", "B", 200, 80, 90000)
    agg.ingest("t2", "A", 50, 20, 30000)
    s = agg.summary()
    assert s["totals"]["in_tokens"] == 350
    assert s["totals"]["usd_micros"] == 170000
    print("OK: cost+token accounting aggregate POC passed; totals=", s["totals"])
