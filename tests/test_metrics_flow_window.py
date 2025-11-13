from metrics.registry import REGISTRY
from router_service.window_update import AIMDController


def test_flow_window_metrics_update():
    c = AIMDController(base=3, max_cap=10, add=1, mult=0.5, target_ms=100, jitter_pct=0.0)
    s = "mx"
    before = REGISTRY.export()["counters"].get("flow_window_adjustments_total", 0)
    # cause increases
    for _ in range(3):
        c.feedback(s, latency_ms=50, ok=True)
    # force decrease
    c.feedback(s, latency_ms=500, ok=True)
    snap = REGISTRY.export()
    assert "flow_window_current" in snap["gauges"]
    assert "flow_window_cap" in snap["gauges"]
    after = snap["counters"].get("flow_window_adjustments_total", 0)
    assert after >= before + 2  # at least two adjustments happened (increase + decrease)
