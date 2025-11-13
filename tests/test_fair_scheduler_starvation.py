import asyncio
import time

import pytest

from router_service.service import FAIR_SCHED


@pytest.mark.asyncio
async def test_starvation_boost():
    # two sessions, one will enqueue early and should eventually be boosted
    FAIR_SCHED.set_weight("SLOW", 1.0)
    FAIR_SCHED.set_weight("FAST", 1.0)

    # Acquire FAST repeatedly keeping SLOW queued
    time.time()

    async def slow_request():
        ok = await FAIR_SCHED.acquire("SLOW", 1, timeout=0.5)
        if ok:
            await FAIR_SCHED.release("SLOW")
            return "SLOW"
        return "SLOW_TIMEOUT"

    async def fast_loop():
        for _ in range(80):
            ok = await FAIR_SCHED.acquire("FAST", 1, timeout=0.01)
            if ok:
                await asyncio.sleep(0.001)
                await FAIR_SCHED.release("FAST")
            await asyncio.sleep(0.001)

    # Kick off slow request first so it waits
    slow_task = asyncio.create_task(slow_request())
    await asyncio.sleep(0.05)  # ensure slow is queued
    await fast_loop()
    res = await slow_task
    assert res == "SLOW", "Starved slow request was not granted"
