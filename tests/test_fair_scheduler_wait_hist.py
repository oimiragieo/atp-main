import asyncio

import pytest

from router_service.service import FAIR_SCHED


@pytest.mark.asyncio
async def test_wait_histogram_records():
    FAIR_SCHED.set_weight("H1", 1.0)

    # Force several queued items by limiting window to 1 and launching tasks rapidly
    async def submit(i):
        ok = await FAIR_SCHED.acquire("H1", 1, timeout=0.2)
        if ok:
            await asyncio.sleep(0.01 if i % 2 == 0 else 0.02)
            await FAIR_SCHED.release("H1")

    tasks = [asyncio.create_task(submit(i)) for i in range(8)]
    await asyncio.gather(*tasks)
    # Export metrics and check histogram buckets exist
    from metrics.registry import REGISTRY

    snap = REGISTRY.export()
    h = snap["histograms"].get("fair_sched_wait_ms")
    assert h, "wait histogram missing"
    total = sum(h["counts"])
    assert total > 0, "expected wait observations"
