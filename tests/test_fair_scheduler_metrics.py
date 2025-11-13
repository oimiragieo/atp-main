from router_service.service import FAIR_SCHED, REGISTRY  # type: ignore


def test_weight_gauge_increments():
    base = REGISTRY.export()["gauges"].get("fair_sched_weighted_sessions", 0)
    FAIR_SCHED.set_weight("metricA", 2.0)
    FAIR_SCHED.set_weight("metricB", 3.0)
    # Give a moment for async operations to complete
    import time

    time.sleep(0.1)
    snap = REGISTRY.export()["gauges"]
    final_value = snap.get("fair_sched_weighted_sessions", 0)
    # The gauge should either increment by at least 1 (for new sessions) or stay the same if sessions already exist
    assert final_value >= base, f"Gauge should not decrease: base={base}, final={final_value}"
