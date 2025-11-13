import asyncio
import os

import pytest


@pytest.mark.asyncio
async def test_lifespan_starts_and_cancels_cleanup(monkeypatch):
    # Ensure required env is present before importing service
    monkeypatch.setenv("ROUTER_ADMIN_API_KEY", os.getenv("ROUTER_ADMIN_API_KEY", "test"))

    # Import after setting env
    import router_service.service as svc  # type: ignore

    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_cleanup():
        started.set()
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    # Swap out the real cleanup coroutine
    monkeypatch.setattr(svc, "_cleanup_expired_sessions", fake_cleanup)

    # Drive lifespan directly via the service-provided context manager
    async with svc.lifespan(svc.app):
        await asyncio.wait_for(started.wait(), timeout=3.0)

    # After client context exits, app shutdown should have cancelled the task
    await asyncio.wait_for(cancelled.wait(), timeout=3.0)
