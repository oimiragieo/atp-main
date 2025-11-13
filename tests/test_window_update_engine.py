from router_service.window_update import AIMDController


def test_aimd_increase_then_decrease():
    c = AIMDController(base=2, max_cap=10, add=1, mult=0.5, target_ms=100)
    s = "sess"
    # start
    assert c.get(s) == 2
    # good latencies => increase
    for _ in range(3):
        c.feedback(s, latency_ms=50, ok=True)
    assert c.get(s) == 5  # 2+1+1+1
    # slow latency triggers multiplicative decrease
    c.feedback(s, latency_ms=300, ok=True)
    assert c.get(s) == 2  # floor after decrease
    # error triggers decrease
    c.feedback(s, latency_ms=50, ok=False)
    assert c.get(s) == 1
