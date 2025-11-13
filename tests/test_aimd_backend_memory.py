from router_service.state_backend import MemoryAIMDBackend
from router_service.window_update import AIMDController


def test_aimd_memory_backend_update_and_prune():
    backend = MemoryAIMDBackend()
    ctrl = AIMDController(backend=backend)
    s = "tenantX"
    before = ctrl.get(s)
    ctrl.feedback(s, latency_ms=200, ok=True)
    after = ctrl.get(s)
    assert after >= before  # additive increase likely
    # Force negative feedback to trigger decrease but not below low water
    ctrl.feedback(s, latency_ms=10000, ok=False)
    lowered = ctrl.get(s)
    assert lowered >= 1
