import importlib
import os

import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.skipif(os.getenv("CI") == "1", reason="skipping redis test in CI unless explicitly enabled")
async def test_redis_backends_basic(monkeypatch):
    # Require redis server for this test; if not available, skip gracefully
    try:
        import redis  # noqa
    except Exception:
        pytest.skip("redis package not installed")
    # Point settings to redis backend then reload modules
    monkeypatch.setenv("ROUTER_ENABLE_TRACING", "0")
    monkeypatch.setenv("ROUTER_STATE_BACKEND", "redis")
    monkeypatch.setenv("ROUTER_REDIS_URL", os.getenv("ROUTER_REDIS_URL", "redis://localhost:6379/0"))
    import router_service.config as cfg

    importlib.reload(cfg)
    import router_service.state_backend as sb

    importlib.reload(sb)
    # Build backends
    sched_backend, aimd_backend = sb.build_backends(cfg.settings)
    # Scheduler weight/served lifecycle
    sched_backend.set_weight("sessX", 2.5)
    assert pytest.approx(sched_backend.get_weight("sessX"), rel=1e-6) == 2.5
    before = sched_backend.snapshot_served().get("sessX", 0)
    sched_backend.inc_served("sessX")
    after = sched_backend.snapshot_served().get("sessX", 0)
    assert after == before + 1
    # AIMD update/get
    cur = aimd_backend.get("sessY")
    aimd_backend.update("sessY", cur + 3)
    assert aimd_backend.get("sessY") == cur + 3
