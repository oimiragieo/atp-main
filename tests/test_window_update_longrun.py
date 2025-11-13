import random

from router_service.window_update import AIMDController


def test_window_update_longrun_invariants():
    c = AIMDController(base=3, max_cap=50, add=2, mult=0.6, target_ms=120, jitter_pct=0.02)
    s = "sim"
    history = []
    for _i in range(1000):
        # emulate latency depending on current size (simple saturation model)
        cur = c.get(s)
        base_latency = 60 + (cur**1.2)  # grows non-linearly
        noise = random.uniform(-10, 40)
        latency = max(1, base_latency + noise)
        ok = latency < 400 and random.random() > 0.02  # occasional explicit failure
        c.feedback(s, latency_ms=latency, ok=ok)
        val = c.get(s)
        history.append(val)
        assert 1 <= val <= 50
    # basic stability heuristic: should have visited both increase and decrease
    assert max(history) - min(history) > 5
    # should not stick at cap for whole run
    assert history.count(50) < 100
