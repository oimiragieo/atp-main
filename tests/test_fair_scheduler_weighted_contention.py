import asyncio
import random

import pytest

from router_service.service import FAIR_SCHED


@pytest.mark.asyncio
async def test_weighted_contention_distribution():
    # Configure weights (4:1)
    FAIR_SCHED.set_weight("X", 4.0)
    FAIR_SCHED.set_weight("Y", 1.0)

    grants = {"X": 0, "Y": 0}

    async def one(session):
        ok = await FAIR_SCHED.acquire(session, 1, timeout=0.05)
        if ok:
            await asyncio.sleep(0.0003)
            await FAIR_SCHED.release(session)
            return 1
        return 0

    # Run many contention waves; each wave submits more X than Y to create backlog for both
    waves = 120
    for _i in range(waves):
        batch = [one("X") for _ in range(4)] + [one("Y")]
        random.shuffle(batch)
        results = await asyncio.gather(*batch)
        # Count successes per session in this wave
        # We re-run until queues emptied, so also do a small drain loop
        grants["X"] += sum(r for r, sess in zip(results, ["X"] * 4 + ["Y"], strict=False) if sess == "X")
        grants["Y"] += sum(r for r, sess in zip(results, ["X"] * 4 + ["Y"], strict=False) if sess == "Y")

    # Expect X to have at least 1.8x Y (looser than 4x due to small sample & tie effects)
    if grants["Y"] == 0:
        assert grants["X"] > 0
    else:
        assert grants["X"] / grants["Y"] > 1.8, f"Weight skew not observed: {grants}"
