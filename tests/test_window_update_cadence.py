from router_service.window_update import AIMDController


def test_window_cadence_growth_and_shrink():
    c = AIMDController(base=2, max_cap=32, add=2, mult=0.5, target_ms=100)
    sess = "s1"
    # rapid successes under target -> growth
    vals = []
    for _ in range(5):
        c.feedback(sess, latency_ms=50, ok=True)
        vals.append(c.get(sess))
    assert vals[-1] > vals[0]
    # few slow / error events -> shrink
    pre = c.get(sess)
    c.feedback(sess, latency_ms=400, ok=True)  # latency breach
    c.feedback(sess, latency_ms=80, ok=False)  # explicit failure
    post = c.get(sess)
    assert post < pre


def test_watermark_floor_and_cap():
    c = AIMDController(
        base=4, max_cap=20, add=3, mult=0.4, target_ms=120, low_water_pct=0.25, high_water_pct=0.5, jitter_pct=0.0
    )
    s = "s2"
    # Inflate up to near high watermark
    for _ in range(20):
        c.feedback(s, latency_ms=50, ok=True)
    cur = c.get(s)
    assert cur <= 20 and cur >= int(20 * 0.5) - 3
    # Force multiple decreases; shouldn't go below low watermark
    for _ in range(5):
        c.feedback(s, latency_ms=500, ok=True)
    low_expected = int(20 * 0.25)
    assert c.get(s) >= low_expected
