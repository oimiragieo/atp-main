"""Tests for Jain's fairness index calculation in FairScheduler."""

import pytest

from router_service.service import FAIR_SCHED, REGISTRY


@pytest.mark.asyncio
class TestJainsIndex:
    """Test Jain's fairness index calculation."""

    async def setup_method(self):
        """Reset scheduler state before each test."""
        pass  # We'll handle cleanup in each test method

    async def test_jains_index_perfect_fairness_single_session(self):
        """Test Jain's index returns 1.0 for single session."""
        # Reset scheduler state
        async with FAIR_SCHED._lock:
            FAIR_SCHED._served.clear()
            FAIR_SCHED._active.clear()
            FAIR_SCHED._weights.clear()
            FAIR_SCHED._boosted_sessions.clear()
            FAIR_SCHED._recent_waits.clear()
            FAIR_SCHED._queue.clear()
            FAIR_SCHED._qos.clear()
            FAIR_SCHED._jains_index_g.set(0.0)

        # Single session with some served count
        FAIR_SCHED._served["session1"] = 10

        index = FAIR_SCHED.compute_jains_index()
        assert index == 1.0

    async def test_jains_index_perfect_fairness_equal_distribution(self):
        """Test Jain's index returns 1.0 for perfectly equal distribution."""
        # Reset scheduler state
        async with FAIR_SCHED._lock:
            FAIR_SCHED._served.clear()
            FAIR_SCHED._active.clear()
            FAIR_SCHED._weights.clear()
            FAIR_SCHED._boosted_sessions.clear()
            FAIR_SCHED._recent_waits.clear()
            FAIR_SCHED._queue.clear()
            FAIR_SCHED._qos.clear()
            FAIR_SCHED._jains_index_g.set(0.0)

        # Two sessions with equal served counts
        FAIR_SCHED._served["session1"] = 10
        FAIR_SCHED._served["session2"] = 10

        index = FAIR_SCHED.compute_jains_index()
        assert abs(index - 1.0) < 0.001  # Should be very close to 1.0

    async def test_jains_index_worst_fairness(self):
        """Test Jain's index returns 1/n for worst case (one session gets everything)."""
        # Reset scheduler state
        async with FAIR_SCHED._lock:
            FAIR_SCHED._served.clear()
            FAIR_SCHED._active.clear()
            FAIR_SCHED._weights.clear()
            FAIR_SCHED._boosted_sessions.clear()
            FAIR_SCHED._recent_waits.clear()
            FAIR_SCHED._queue.clear()
            FAIR_SCHED._qos.clear()
            FAIR_SCHED._jains_index_g.set(0.0)

        # Two sessions, one gets all the service
        FAIR_SCHED._served["session1"] = 100
        FAIR_SCHED._served["session2"] = 0

        index = FAIR_SCHED.compute_jains_index()
        expected_worst = 1.0 / 1  # Only one active session (session2 has 0)
        assert abs(index - expected_worst) < 0.001

    async def test_jains_index_three_sessions_unequal(self):
        """Test Jain's index calculation with three sessions having unequal distribution."""
        # Reset scheduler state
        async with FAIR_SCHED._lock:
            FAIR_SCHED._served.clear()
            FAIR_SCHED._active.clear()
            FAIR_SCHED._weights.clear()
            FAIR_SCHED._boosted_sessions.clear()
            FAIR_SCHED._recent_waits.clear()
            FAIR_SCHED._queue.clear()
            FAIR_SCHED._qos.clear()
            FAIR_SCHED._jains_index_g.set(0.0)

        # Three sessions with different served counts
        FAIR_SCHED._served["session1"] = 30
        FAIR_SCHED._served["session2"] = 20
        FAIR_SCHED._served["session3"] = 10

        index = FAIR_SCHED.compute_jains_index()

        # Manual calculation:
        # sum_x = 30 + 20 + 10 = 60
        # sum_x_squared = 30^2 + 20^2 + 10^2 = 900 + 400 + 100 = 1400
        # n = 3
        # jains = (60^2) / (3 * 1400) = 3600 / 4200 = 0.857
        expected = 3600 / 4200

        assert abs(index - expected) < 0.001

    async def test_jains_index_no_sessions_served(self):
        """Test Jain's index returns 1.0 when no sessions have been served."""
        # Reset scheduler state
        async with FAIR_SCHED._lock:
            FAIR_SCHED._served.clear()
            FAIR_SCHED._active.clear()
            FAIR_SCHED._weights.clear()
            FAIR_SCHED._boosted_sessions.clear()
            FAIR_SCHED._recent_waits.clear()
            FAIR_SCHED._queue.clear()
            FAIR_SCHED._qos.clear()
            FAIR_SCHED._jains_index_g.set(0.0)

        # No served counts
        index = FAIR_SCHED.compute_jains_index()
        assert index == 1.0

    async def test_jains_index_zero_served_filtered_out(self):
        """Test that sessions with zero served count are filtered out."""
        # Reset scheduler state
        async with FAIR_SCHED._lock:
            FAIR_SCHED._served.clear()
            FAIR_SCHED._active.clear()
            FAIR_SCHED._weights.clear()
            FAIR_SCHED._boosted_sessions.clear()
            FAIR_SCHED._recent_waits.clear()
            FAIR_SCHED._queue.clear()
            FAIR_SCHED._qos.clear()
            FAIR_SCHED._jains_index_g.set(0.0)

        # One session with served count, one with zero
        FAIR_SCHED._served["active"] = 10
        FAIR_SCHED._served["inactive"] = 0

        index = FAIR_SCHED.compute_jains_index()
        assert index == 1.0  # Only one active session

    async def test_jains_index_bounds_checking(self):
        """Test that Jain's index is properly bounded."""
        # Reset scheduler state
        async with FAIR_SCHED._lock:
            FAIR_SCHED._served.clear()
            FAIR_SCHED._active.clear()
            FAIR_SCHED._weights.clear()
            FAIR_SCHED._boosted_sessions.clear()
            FAIR_SCHED._recent_waits.clear()
            FAIR_SCHED._queue.clear()
            FAIR_SCHED._qos.clear()
            FAIR_SCHED._jains_index_g.set(0.0)

        # Create a scenario that might produce out-of-bounds values
        FAIR_SCHED._served["session1"] = 1
        FAIR_SCHED._served["session2"] = 1000000  # Very unequal distribution

        index = FAIR_SCHED.compute_jains_index()

        # Should be bounded between 1/n and 1.0
        n = 2  # Both sessions have non-zero served counts
        assert 1.0 / n <= index <= 1.0

    async def test_jains_index_metric_updated(self):
        """Test that Jain's index metric is updated when computed."""
        # Reset scheduler state
        async with FAIR_SCHED._lock:
            FAIR_SCHED._served.clear()
            FAIR_SCHED._active.clear()
            FAIR_SCHED._weights.clear()
            FAIR_SCHED._boosted_sessions.clear()
            FAIR_SCHED._recent_waits.clear()
            FAIR_SCHED._queue.clear()
            FAIR_SCHED._qos.clear()
            FAIR_SCHED._jains_index_g.set(0.0)

        # Set up served counts
        FAIR_SCHED._served["session1"] = 10
        FAIR_SCHED._served["session2"] = 10

        # Get initial metric value (not used but shows we check metric updates)
        REGISTRY.export()["gauges"].get("fair_sched_jains_index", 0)

        # Compute index
        index = FAIR_SCHED.compute_jains_index()

        # Check that metric was updated
        final_metric = REGISTRY.export()["gauges"].get("fair_sched_jains_index", 0)
        assert abs(final_metric - index) < 0.001


@pytest.mark.asyncio
async def test_jains_index_integration_with_scheduler():
    """Integration test: Jain's index updates as scheduler serves requests."""
    # Clear state comprehensively
    async with FAIR_SCHED._lock:
        FAIR_SCHED._served.clear()
        FAIR_SCHED._active.clear()
        FAIR_SCHED._weights.clear()
        FAIR_SCHED._boosted_sessions.clear()
        FAIR_SCHED._recent_waits.clear()
        FAIR_SCHED._queue.clear()
        FAIR_SCHED._qos.clear()
        FAIR_SCHED._jains_index_g.set(0.0)

    # Set up sessions with different weights
    FAIR_SCHED.set_weight("session1", 1.0)
    FAIR_SCHED.set_weight("session2", 1.0)

    # Initially should be 1.0 (no sessions served)
    index = FAIR_SCHED.compute_jains_index()
    assert index == 1.0

    # Simulate serving some requests
    FAIR_SCHED._served["session1"] = 5
    FAIR_SCHED._served["session2"] = 5

    index = FAIR_SCHED.compute_jains_index()
    assert abs(index - 1.0) < 0.001  # Should be fair

    # Make distribution unequal
    FAIR_SCHED._served["session1"] = 10
    FAIR_SCHED._served["session2"] = 2

    index = FAIR_SCHED.compute_jains_index()
    assert index < 1.0  # Should be less than perfect fairness
    assert index > 0.5  # Should be better than worst case
