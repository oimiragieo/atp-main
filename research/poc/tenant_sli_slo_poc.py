"""Per-tenant SLI/SLO + alert evaluation POC.
Computes rolling error rate and latency percentiles per tenant and evaluates against SLOs.
"""

from __future__ import annotations

import random
from collections import defaultdict, deque


class MetricsWindow:
    def __init__(self, max_len=200):
        self.records: deque[tuple[float, float, bool]] = deque(maxlen=max_len)  # (latency_ms, cost_usd_micros, error)

    def add(self, latency_ms: float, cost: float, error: bool):
        self.records.append((latency_ms, cost, error))

    def error_rate(self):
        if not self.records:
            return 0.0
        return sum(1 for *_, e in self.records if e) / len(self.records)

    def p95(self):
        if not self.records:
            return 0.0
        vals = sorted(r[0] for r in self.records)
        idx = int(0.95 * (len(vals) - 1))
        return vals[idx]


class TenantSLIEvaluator:
    def __init__(self, window=200):
        self.windows: dict[str, MetricsWindow] = defaultdict(lambda: MetricsWindow(window))
        self.alerts: list[str] = []

    def record(self, tenant: str, latency_ms: float, cost_usd_micros: float, error: bool):
        self.windows[tenant].add(latency_ms, cost_usd_micros, error)

    def evaluate(self, slo_error_rate=0.05, slo_p95=800):
        self.alerts.clear()
        for t, w in self.windows.items():
            if w.error_rate() > slo_error_rate:
                self.alerts.append(f"ALERT:{t}:error_rate")
            if w.p95() > slo_p95:
                self.alerts.append(f"ALERT:{t}:latency_p95")
        return self.alerts


if __name__ == "__main__":
    ev = TenantSLIEvaluator()
    random.seed(0)
    for i in range(150):
        ev.record("tenantA", latency_ms=random.randint(50, 120), cost_usd_micros=50000, error=(i % 40 == 0))
        ev.record("tenantB", latency_ms=random.randint(700, 900), cost_usd_micros=70000, error=(i % 10 == 0))
    alerts = ev.evaluate(slo_error_rate=0.05, slo_p95=600)
    assert any(a.startswith("ALERT:tenantB:latency") for a in alerts)
    assert any(a.startswith("ALERT:tenantB:error_rate") for a in alerts)
    # tenantA should not breach latency p95 threshold 600? check
    assert not any(a.startswith("ALERT:tenantA:latency") for a in alerts)
    print("OK: tenant SLI/SLO POC passed; alerts=", alerts)
