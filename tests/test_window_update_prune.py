import time

from router_service.window_update import AIMDController


def test_prune_idle_sessions():
    c = AIMDController(base=2, max_cap=10)
    # touch sessions
    c.feedback("a", 50, ok=True)
    c.feedback("b", 50, ok=True)
    # simulate idle by manually adjusting last_update
    past = time.time() - (c.idle_ttl_s + 10)
    c._states["a"].last_update = past  # type: ignore
    pruned = c.prune_idle(now=time.time())
    assert pruned == 1
    assert "a" not in c._states and "b" in c._states
