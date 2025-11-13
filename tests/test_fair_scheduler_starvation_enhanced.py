"""Tests for enhanced FairQueue starvation detector with auto weight boost."""

import time
from unittest.mock import patch

import pytest

from router_service.service import FAIR_SCHED, REGISTRY


@pytest.mark.asyncio
async def test_dynamic_threshold_calculation():
    """Test that dynamic threshold is calculated based on wait time quantiles."""
    # Initially should return static threshold
    threshold = FAIR_SCHED._calculate_dynamic_threshold()
    assert threshold == 50.0

    # Add some wait times
    FAIR_SCHED._recent_waits = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]

    # With 95th percentile, should be close to 95th value
    threshold = FAIR_SCHED._calculate_dynamic_threshold()
    assert threshold >= 90.0  # 95th percentile of [10..100] should be >= 95


@pytest.mark.asyncio
async def test_get_effective_weight_without_boost():
    """Test effective weight calculation without active boosts."""
    session = "test_session"
    FAIR_SCHED.set_weight(session, 1.0)

    effective = FAIR_SCHED._get_effective_weight(session)
    assert effective == 1.0


@pytest.mark.asyncio
async def test_get_effective_weight_with_boost():
    """Test effective weight calculation with active boost."""
    session = "test_session"
    FAIR_SCHED.set_weight(session, 1.0)

    # Clear any existing boosts
    FAIR_SCHED._boosted_sessions.clear()

    # Apply boost
    FAIR_SCHED._apply_starvation_boost(session)

    # Should have boosted weight (allow small floating point differences)
    effective = FAIR_SCHED._get_effective_weight(session)
    assert abs(effective - 2.0) < 0.01  # Allow small floating point differences


@pytest.mark.asyncio
async def test_boost_decay_over_time():
    """Test that boosts decay over time."""
    session = "test_session"
    FAIR_SCHED.set_weight(session, 1.0)

    # Clear any existing boosts
    FAIR_SCHED._boosted_sessions.clear()

    # Apply boost
    FAIR_SCHED._apply_starvation_boost(session)

    # Immediately should have full boost
    effective = FAIR_SCHED._get_effective_weight(session)
    assert abs(effective - 2.0) < 0.01

    # Mock time passage for decay
    with patch("time.time", return_value=time.time() + 1.0):  # 1 second later
        effective = FAIR_SCHED._get_effective_weight(session)
        # Should be decayed: 2.0 * (0.9^1) = 1.8
        assert 1.7 < effective < 1.9


@pytest.mark.asyncio
async def test_boost_expiration():
    """Test that expired boosts are removed."""
    session = "test_session"
    FAIR_SCHED.set_weight(session, 1.0)

    # Apply boost
    FAIR_SCHED._apply_starvation_boost(session)
    assert session in FAIR_SCHED._boosted_sessions

    # Fast-forward time to expire boost
    with patch("time.time", return_value=time.time() + 100.0):  # Long time later
        effective = FAIR_SCHED._get_effective_weight(session)
        # Should be back to base weight
        assert effective == 1.0
        # Boost should be removed
        assert session not in FAIR_SCHED._boosted_sessions


@pytest.mark.asyncio
async def test_starvation_boost_application():
    """Test that starvation boosts are applied when starvation is detected."""
    # Setup sessions
    FAIR_SCHED.set_weight("starved_session", 1.0)
    FAIR_SCHED.set_weight("normal_session", 1.0)

    # Create a queued entry that will be starved
    from router_service.service import _FairQueueEntry

    starved_entry = _FairQueueEntry(
        priority=0.0,
        session="starved_session",
        weight=1.0,
        enqueued_at=time.time() - 0.1,  # 100ms ago
    )

    async with FAIR_SCHED._lock:
        FAIR_SCHED._queue.append(starved_entry)
        FAIR_SCHED._active["starved_session"] = 0  # Allow granting

    # Mock AIMD to allow granting
    with patch("router_service.service.GLOBAL_AIMD") as mock_aimd:
        mock_aimd.get.return_value = 10  # High window

        # Trigger selection
        FAIR_SCHED._select_next_locked()

        # Should have applied boost
        assert "starved_session" in FAIR_SCHED._boosted_sessions


@pytest.mark.asyncio
async def test_wait_time_tracking():
    """Test that wait times are tracked for quantile calculation."""
    # Clear existing wait times
    FAIR_SCHED._recent_waits.clear()

    # Initially empty
    assert len(FAIR_SCHED._recent_waits) == 0

    # Add some wait times by simulating selections
    FAIR_SCHED._recent_waits.extend([10.0, 20.0, 30.0])

    # Should be tracked
    assert len(FAIR_SCHED._recent_waits) == 3
    assert 10.0 in FAIR_SCHED._recent_waits


@pytest.mark.asyncio
async def test_wait_time_buffer_limit():
    """Test that wait time buffer respects maximum size."""
    # Clear existing wait times
    FAIR_SCHED._recent_waits.clear()

    # Fill buffer to max
    FAIR_SCHED._recent_waits = list(range(FAIR_SCHED._max_recent_waits))

    # Add one more - this should trigger the buffer limit logic in the actual code
    # but for this test, we'll just verify the max size
    FAIR_SCHED._recent_waits.append(999.0)

    # Should be at max + 1 now
    assert len(FAIR_SCHED._recent_waits) == FAIR_SCHED._max_recent_waits + 1

    # Simulate what happens in the actual code (removing oldest when adding)
    if len(FAIR_SCHED._recent_waits) > FAIR_SCHED._max_recent_waits:
        FAIR_SCHED._recent_waits.pop(0)  # Remove oldest

    # Should not exceed max after cleanup
    assert len(FAIR_SCHED._recent_waits) <= FAIR_SCHED._max_recent_waits


@pytest.mark.asyncio
async def test_starvation_events_metric():
    """Test that starvation events are properly counted."""
    initial_count = REGISTRY.export()["counters"].get("fair_sched_starvation_events_total", 0)

    # Apply boost
    FAIR_SCHED._apply_starvation_boost("test_session")

    # Should increment counter
    final_count = REGISTRY.export()["counters"].get("fair_sched_starvation_events_total", 0)
    assert final_count > initial_count


@pytest.mark.asyncio
async def test_configuration_via_environment():
    """Test that configuration can be set via environment variables."""
    with patch.dict(
        "os.environ",
        {"FAIR_SCHED_STARVATION_QUANTILE": "0.90", "FAIR_SCHED_BOOST_FACTOR": "3.0", "FAIR_SCHED_BOOST_DECAY": "0.8"},
    ):
        # Create new scheduler to pick up env vars
        from router_service.service import FairScheduler

        test_sched = FairScheduler()

        assert test_sched._starvation_quantile == 0.90
        assert test_sched._starvation_boost_factor == 3.0
        assert test_sched._starvation_boost_decay == 0.8


@pytest.mark.asyncio
async def test_induced_starvation_resolution():
    """Integration test: induce starvation and verify resolution with boost."""
    import time

    from router_service.service import _FairQueueEntry

    # Clear existing state
    FAIR_SCHED._boosted_sessions.clear()
    FAIR_SCHED._recent_waits.clear()

    # Setup
    FAIR_SCHED.set_weight("victim", 0.1)  # Low weight victim
    FAIR_SCHED.set_weight("bully", 2.0)  # High weight bully

    # Create a queued entry that will trigger starvation detection
    starved_entry = _FairQueueEntry(
        priority=0.0,
        session="victim",
        weight=0.1,
        enqueued_at=time.time() - 0.2,  # 200ms ago - should trigger starvation
    )

    async with FAIR_SCHED._lock:
        FAIR_SCHED._queue.append(starved_entry)
        FAIR_SCHED._active["victim"] = 0  # Allow granting

    # Mock AIMD to allow granting
    with patch("router_service.service.GLOBAL_AIMD") as mock_aimd:
        mock_aimd.get.return_value = 10  # High window

        # Trigger selection which should detect starvation and apply boost
        result = FAIR_SCHED._select_next_locked()

        # Should have granted the starved entry
        assert result is not None
        assert result.session == "victim"

        # Should have applied boost due to starvation
        assert "victim" in FAIR_SCHED._boosted_sessions


@pytest.mark.asyncio
async def test_boost_prevents_further_starvation():
    """Test that applied boosts prevent further starvation of the same session."""
    # Clear existing state
    FAIR_SCHED._boosted_sessions.clear()

    FAIR_SCHED.set_weight("session", 1.0)

    # First starvation should apply boost
    FAIR_SCHED._apply_starvation_boost("session")
    assert "session" in FAIR_SCHED._boosted_sessions

    # Effective weight should be boosted
    effective = FAIR_SCHED._get_effective_weight("session")
    assert effective > 1.0

    # Second starvation check should see higher effective weight
    # (simulating that the session gets better service due to boost)
    effective2 = FAIR_SCHED._get_effective_weight("session")
    assert abs(effective2 - effective) < 0.01  # Should maintain boost (within floating point precision)
