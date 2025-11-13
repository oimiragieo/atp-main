import pytest

from router_service.service import FAIR_SCHED, GLOBAL_AIMD


@pytest.mark.asyncio
async def test_fair_scheduler_fastpath():
    sess = "tenantA"
    win = GLOBAL_AIMD.get(sess)
    # Acquire up to window
    granted = 0
    for _ in range(win):
        ok = await FAIR_SCHED.acquire(sess, win, timeout=0.0)
        if ok:
            granted += 1
    assert granted == win
    # Next immediate acquire should fail (non-blocking) and not exceed window
    ok2 = await FAIR_SCHED.acquire(sess, win, timeout=0.0)
    assert not ok2
    # Release one and ensure next acquire succeeds
    await FAIR_SCHED.release(sess)
    ok3 = await FAIR_SCHED.acquire(sess, win, timeout=0.0)
    assert ok3
