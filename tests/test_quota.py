import logging
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "memory-gateway")))
from quota import HybridQuotaManager, QuotaManager

# Configure test logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def test_legacy_quota():
    """Test legacy quota manager."""
    qm = QuotaManager(max_items=3, max_bytes=10)
    now = time.time()
    ok, ev = qm.put("ns", "a", size=3, ttl_s=None, now=now)
    assert ok and ev == 0
    ok, ev = qm.put("ns", "b", size=4, ttl_s=1, now=now)
    assert ok and ev == 0
    ok, ev = qm.put("ns", "c", size=4, ttl_s=None, now=now)
    # bytes: 3+4+4 = 11 > 10 → should evict oldest until within quota
    assert ok is True and ev >= 1
    # advance time for TTL expiry
    ok, ev = qm.put("ns", "d", size=3, ttl_s=None, now=now + 2)
    assert ok is True  # 'b' should have expired
    logger.info("OK: legacy quota/GC POC passed")


def test_hybrid_quota_burst_allowed():
    """Test hybrid quota manager allows bursts within limits."""
    qm = HybridQuotaManager(max_items=10, max_bytes=100, window_size_s=60.0, sustained_rps=2.0, burst_rps=10.0)

    now = time.time()

    # Should allow burst of requests initially
    results = []
    for i in range(5):  # Burst of 5 requests
        ok, ev, reason = qm.put("ns", f"key{i}", size=5, ttl_s=None, now=now)
        results.append((ok, reason))

    # All should be allowed (burst)
    assert all(ok for ok, _ in results), f"Burst requests failed: {results}"
    assert all(reason == "ok" for _, reason in results), f"Unexpected reasons: {results}"
    logger.info("OK: hybrid quota burst allowed")


def test_hybrid_quota_sustained_throttling():
    """Test hybrid quota manager throttles sustained high rate."""
    qm = HybridQuotaManager(max_items=100, max_bytes=1000, window_size_s=1.0, sustained_rps=2.0, burst_rps=5.0)

    now = time.time()
    allowed_count = 0
    throttled_count = 0

    # Simulate requests over time
    for i in range(10):
        ok, _, reason = qm.put("ns", f"key{i}", size=1, ttl_s=None, now=now + i * 0.1)
        if ok:
            allowed_count += 1
        else:
            throttled_count += 1
            assert reason in ["rate_limit_sustained", "rate_limit_burst"]

    # Should allow some burst initially, then throttle
    assert allowed_count > 0, "Should allow some requests"
    assert throttled_count > 0, "Should throttle some requests"
    logger.info(f"OK: hybrid quota sustained throttling (allowed: {allowed_count}, throttled: {throttled_count})")


def test_hybrid_quota_quota_exceeded():
    """Test hybrid quota manager handles quota exceeded."""
    qm = HybridQuotaManager(max_items=2, max_bytes=5, window_size_s=60.0, sustained_rps=10.0, burst_rps=20.0)

    now = time.time()

    # Fill up quota with items that can't be evicted
    ok1, _, _ = qm.put("ns", "key1", size=3, ttl_s=None, now=now)
    ok2, _, _ = qm.put("ns", "key2", size=3, ttl_s=None, now=now)
    ok3, _, reason3 = qm.put("ns", "key3", size=3, ttl_s=None, now=now)  # 3+3+3=9 > 5 bytes

    assert ok1 and ok2, "First two puts should succeed"
    # The third put should either fail or evict items
    if not ok3:
        assert reason3 == "quota_exceeded", f"Expected quota_exceeded, got {reason3}"
    else:
        # If it succeeded, it must have evicted something
        assert reason3 == "ok", f"Unexpected success reason: {reason3}"
    logger.info("OK: hybrid quota quota handling")


def main():
    test_legacy_quota()
    test_hybrid_quota_burst_allowed()
    test_hybrid_quota_sustained_throttling()
    test_hybrid_quota_quota_exceeded()
    logger.info("All quota tests passed!")


if __name__ == "__main__":
    main()
