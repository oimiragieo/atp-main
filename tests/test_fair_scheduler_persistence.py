import json

from router_service.service import (
    _COUNTERS_FILE,
    FAIR_SCHED,
    REGISTRY,  # type: ignore
    _load_counters,
)

# We'll simulate one iteration of persistence manually rather than running thread loop.


def test_fair_scheduler_weights_persist_and_load(monkeypatch):
    FAIR_SCHED.set_weight("persistA", 7.5)
    FAIR_SCHED.set_weight("persistB", 3.3)
    # Force a single write by invoking private logic similar to loop body
    snap = REGISTRY.export()
    data = {
        "registry": snap,
        "promotion": 0,
        "demotion": 0,
        "rate_limit_dropped": 0,
        "lat_buckets": [],
        "fair_weights": FAIR_SCHED.snapshot_weights(),
    }
    with open(_COUNTERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)
    # Reset weights to defaults to ensure load repopulates
    FAIR_SCHED._weights.clear()  # type: ignore
    _load_counters()
    snap2 = FAIR_SCHED.snapshot_weights()
    assert snap2.get("persistA") == 7.5
    assert snap2.get("persistB") == 3.3
