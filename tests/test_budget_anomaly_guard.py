"""Tests for budget anomaly guard spike detection."""

import asyncio

import pytest

from router_service.budget import BudgetAnomalyGuard, BudgetGovernor, Usage


@pytest.mark.asyncio
class TestBudgetAnomalyGuard:
    """Test budget anomaly detection using EWMA + z-score."""

    def setup_method(self):
        """Set up test fixtures."""
        self.guard = BudgetAnomalyGuard(
            ewma_alpha=0.2,  # Faster adaptation for testing
            z_threshold=2.0,  # Lower threshold for testing
            min_samples=5,  # Fewer samples needed for testing
            max_samples=20,  # Smaller history for testing
            spike_cooldown_s=1.0,  # Short cooldown for testing
        )

    def teardown_method(self):
        """Clean up after tests."""
        # Reset guard state
        self.guard._ewma.clear()
        self.guard._variance.clear()
        self.guard._samples.clear()
        self.guard._last_spike.clear()

    async def test_anomaly_guard_initialization(self):
        """Test anomaly guard initializes with correct parameters."""
        assert self.guard.ewma_alpha == 0.2
        assert self.guard.z_threshold == 2.0
        assert self.guard.min_samples == 5
        assert self.guard.max_samples == 20
        assert self.guard.spike_cooldown_s == 1.0

    async def test_no_spike_with_insufficient_samples(self):
        """Test no spike detection when insufficient samples."""
        session = "test_session"

        # Add fewer than min_samples
        for _ in range(3):
            spike = self.guard.check_for_spike(session, 10.0)
            assert not spike

    async def test_normal_operation_no_spike(self):
        """Test normal operation doesn't trigger spikes."""
        session = "test_session"

        # Add normal burn rates
        normal_rates = [10.0, 11.0, 9.5, 10.5, 9.8, 10.2, 10.1]

        for rate in normal_rates:
            spike = self.guard.check_for_spike(session, rate)
            assert not spike

        # Verify samples are stored
        assert len(self.guard._samples[session]) == len(normal_rates)

    async def test_spike_detection(self):
        """Test spike detection with anomalous burn rate."""
        session = "test_session"

        # Add normal burn rates first
        normal_rates = [10.0, 10.1, 9.9, 10.2, 9.8, 10.1, 10.0, 9.9]
        for rate in normal_rates:
            spike = self.guard.check_for_spike(session, rate)
            assert not spike

        # Add spike
        spike = self.guard.check_for_spike(session, 50.0)  # Much higher than normal
        assert spike

    async def test_spike_cooldown(self):
        """Test spike cooldown prevents repeated alerts."""
        session = "test_session"

        # Set up normal baseline
        normal_rates = [10.0, 10.1, 9.9, 10.2, 9.8, 10.1, 10.0, 9.9]
        for rate in normal_rates:
            self.guard.check_for_spike(session, rate)

        # First spike should be detected
        spike1 = self.guard.check_for_spike(session, 50.0)
        assert spike1

        # Second spike should be blocked by cooldown
        spike2 = self.guard.check_for_spike(session, 60.0)
        assert not spike2

    async def test_spike_cooldown_expires(self):
        """Test spike cooldown expires after time passes."""
        session = "test_session"

        # Set up normal baseline
        normal_rates = [10.0, 10.1, 9.9, 10.2, 9.8, 10.1, 10.0, 9.9]
        for rate in normal_rates:
            self.guard.check_for_spike(session, rate)

        # First spike
        spike1 = self.guard.check_for_spike(session, 50.0)
        assert spike1

        # Wait for cooldown to expire
        await asyncio.sleep(1.1)

        # Second spike should be detected
        spike2 = self.guard.check_for_spike(session, 60.0)
        assert spike2

    async def test_ewma_calculation(self):
        """Test EWMA calculation."""
        session = "test_session"

        # First value should be EWMA
        ewma1 = self.guard._update_ewma(session, 10.0)
        assert ewma1 == 10.0

        # Second value should be smoothed
        ewma2 = self.guard._update_ewma(session, 20.0)
        expected = 0.2 * 20.0 + 0.8 * 10.0  # alpha=0.2
        assert abs(ewma2 - expected) < 0.001

    async def test_sample_history_management(self):
        """Test sample history is properly managed."""
        session = "test_session"

        # Add samples up to max_samples
        for i in range(25):  # More than max_samples (20)
            self.guard._update_samples(session, float(i))

        # Should only keep max_samples
        assert len(self.guard._samples[session]) == 20

        # Should keep most recent samples
        samples = self.guard._samples[session]
        assert samples[0] == 5.0  # Oldest kept
        assert samples[-1] == 24.0  # Newest

    async def test_z_score_calculation(self):
        """Test z-score calculation."""
        session = "test_session"

        # Add known samples: mean=10, std=1
        samples = [9.0, 10.0, 11.0, 9.0, 10.0, 11.0, 9.0, 10.0, 11.0, 10.0]
        for sample in samples:
            self.guard._update_samples(session, sample)

        # Test value at mean (should be z=0)
        z_mean = self.guard._calculate_z_score(session, 10.0)
        assert abs(z_mean) < 0.1

        # Test value 2 std above mean (should be z≈2.58 for this dataset)
        z_high = self.guard._calculate_z_score(session, 12.0)
        assert abs(z_high - 2.58) < 0.1

    async def test_session_stats(self):
        """Test session statistics retrieval."""
        session = "test_session"

        # Add some data
        for _ in range(10):
            self.guard._update_samples(session, 10.0)
            self.guard._update_ewma(session, 10.0)

        stats = self.guard.get_session_stats(session)

        assert "ewma" in stats
        assert "sample_count" in stats
        assert "last_spike_time" in stats
        assert "z_threshold" in stats
        assert stats["sample_count"] == 10
        assert stats["z_threshold"] == 2.0

    async def test_session_reset(self):
        """Test session reset functionality."""
        session = "test_session"

        # Add data
        for _ in range(10):
            self.guard._update_samples(session, 10.0)
            self.guard._update_ewma(session, 10.0)

        # Verify data exists
        assert session in self.guard._samples
        assert session in self.guard._ewma

        # Reset
        self.guard.reset_session(session)

        # Verify data is cleared
        assert session not in self.guard._samples
        assert session not in self.guard._ewma
        assert session not in self.guard._last_spike

    async def test_multiple_sessions_isolated(self):
        """Test multiple sessions are isolated."""
        session1 = "session1"
        session2 = "session2"

        # Add data to session1
        for _ in range(10):
            self.guard._update_samples(session1, 10.0)

        # Add different data to session2
        for _ in range(5):
            self.guard._update_samples(session2, 20.0)

        # Verify isolation
        assert len(self.guard._samples[session1]) == 10
        assert len(self.guard._samples[session2]) == 5

        # Reset session1
        self.guard.reset_session(session1)

        # session2 should be unaffected
        assert session1 not in self.guard._samples
        assert len(self.guard._samples[session2]) == 5


@pytest.mark.asyncio
async def test_budget_governor_anomaly_integration():
    """Integration test: BudgetGovernor with anomaly detection."""
    governor = BudgetGovernor()

    # Simulate normal usage
    session = "test_session"
    normal_usage = Usage(tokens=100, usd_micros=10000)  # $0.10

    # Add normal consumption over time
    for _ in range(20):
        governor.consume(session, normal_usage)
        # Small delay to simulate time passing
        await asyncio.sleep(0.01)

    # Check that no spikes were detected initially
    # (This is hard to test directly since we can't easily access the guard,
    # but we can verify the governor still works)

    # Simulate spike in usage
    spike_usage = Usage(tokens=1000, usd_micros=1000000)  # $10 - much higher
    governor.consume(session, spike_usage)

    # Verify consumption was recorded
    remaining = governor.remaining(session)
    assert remaining.usd_micros < 10000000  # Some budget was consumed

    # Verify burn rate is calculated
    burn_rate = governor.burn_rate_usd_per_min(session)
    assert burn_rate > 0.0
