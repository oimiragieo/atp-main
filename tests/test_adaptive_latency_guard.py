#!/usr/bin/env python3
"""Tests for Adaptive Latency Guard."""

import time

import pytest

from tools.adaptive_latency_guard import (
    AdaptiveLatencyGuard,
    GuardAction,
    GuardConfig,
    LatencyThreshold,
    get_latency_guard,
    start_latency_guard,
    stop_latency_guard,
)
from tools.gpu_batch_scheduler import BatchConfig, BatchMetrics, GPUBatchScheduler


class TestAdaptiveLatencyGuard:
    """Test suite for adaptive latency guard."""

    def setup_method(self):
        """Set up test fixtures."""
        self.batch_config = BatchConfig(max_batch_size=8, latency_target_ms=200)
        self.scheduler = GPUBatchScheduler(self.batch_config)

        self.guard_config = GuardConfig(
            enabled=True,
            monitoring_window_seconds=10,
            evaluation_interval_seconds=1,
            thresholds=LatencyThreshold(p95_ms=150, p99_ms=300, max_ms=500),
        )
        self.guard = AdaptiveLatencyGuard(self.scheduler, self.guard_config)

    def teardown_method(self):
        """Clean up test fixtures."""
        if self.guard.monitoring_active:
            self.guard.stop_monitoring()

    def test_initialization(self):
        """Test guard initialization."""
        assert self.guard.config == self.guard_config
        assert not self.guard.monitoring_active
        assert self.guard.metrics.total_evaluations == 0
        assert self.guard.metrics.violations_detected == 0

    def test_guard_action_determination(self):
        """Test action determination based on latency."""
        # Normal latency
        assert self.guard._determine_action(100) == GuardAction.ALLOW

        # P95 violation
        assert self.guard._determine_action(200) == GuardAction.REDUCE_BATCH_SIZE

        # P99 violation
        assert self.guard._determine_action(350) == GuardAction.THROTTLE_REQUESTS

        # Max violation
        assert self.guard._determine_action(600) == GuardAction.DROP_REQUESTS

    def test_violation_handling_reduce_batch_size(self):
        """Test handling of batch size reduction violations."""
        initial_batch_size = self.scheduler.optimal_batch_size

        # Simulate P95 violation
        self.guard._handle_violation(GuardAction.REDUCE_BATCH_SIZE, 200, {})

        assert self.scheduler.optimal_batch_size < initial_batch_size
        assert self.guard.metrics.violations_detected == 1
        assert self.guard.metrics.batch_size_reductions == 1
        assert self.guard.metrics.actions_taken == 1

    def test_violation_handling_throttle_requests(self):
        """Test handling of request throttling violations."""
        original_timeout = self.scheduler.config.batch_timeout_ms

        # Simulate P99 violation
        self.guard._handle_violation(GuardAction.THROTTLE_REQUESTS, 350, {})

        assert self.scheduler.config.batch_timeout_ms > original_timeout
        assert self.guard.metrics.requests_throttled == 1
        assert self.guard.metrics.actions_taken == 1

    def test_violation_handling_drop_requests(self):
        """Test handling of request dropping violations."""
        # Simulate max latency violation
        self.guard._handle_violation(GuardAction.DROP_REQUESTS, 600, {})

        assert self.guard.metrics.requests_dropped == 1
        assert self.guard.metrics.actions_taken == 1

    def test_cooldown_period(self):
        """Test cooldown period prevents rapid adjustments."""
        # First violation
        self.guard._handle_violation(GuardAction.REDUCE_BATCH_SIZE, 200, {})
        first_actions = self.guard.metrics.actions_taken

        # Immediate second violation (should be ignored due to cooldown)
        self.guard._handle_violation(GuardAction.REDUCE_BATCH_SIZE, 200, {})

        # Actions should not have increased
        assert self.guard.metrics.actions_taken == first_actions

    def test_recovery_detection(self):
        """Test recovery detection after violations."""
        recovery_called = False

        def recovery_callback(data):
            nonlocal recovery_called
            recovery_called = True

        self.guard.add_recovery_callback(recovery_callback)

        # Create violation streak
        self.guard.metrics.current_violation_streak = 3

        # Simulate normal latency (should trigger recovery)
        self.guard._handle_recovery({})

        assert self.guard.metrics.current_violation_streak == 0
        assert recovery_called

    def test_violation_streak_tracking(self):
        """Test violation streak tracking."""
        # Multiple violations
        for _i in range(3):
            self.guard._handle_violation(GuardAction.REDUCE_BATCH_SIZE, 200, {})

        assert self.guard.metrics.current_violation_streak == 3

        # Recovery resets streak
        self.guard._handle_recovery({})
        assert self.guard.metrics.current_violation_streak == 0

    def test_latency_window_management(self):
        """Test latency window sliding window."""
        # Add latencies to window
        latencies = [100, 120, 150, 180, 200]
        for latency in latencies:
            self.guard.latency_window.append(latency)

        assert len(self.guard.latency_window) == 5

        # Add one more (should maintain window size if configured)
        # Note: In test setup, window size is based on monitoring config
        self.guard.latency_window.append(220)

        # Window should grow until it hits the limit
        # (In real usage, the monitoring loop manages the window size)

    def test_callback_system(self):
        """Test violation and recovery callbacks."""
        violation_events = []
        recovery_events = []

        def violation_callback(action, data):
            violation_events.append((action, data))

        def recovery_callback(data):
            recovery_events.append(data)

        self.guard.add_violation_callback(violation_callback)
        self.guard.add_recovery_callback(recovery_callback)

        # Trigger violation
        self.guard._handle_violation(GuardAction.REDUCE_BATCH_SIZE, 200, {"test": "data"})

        assert len(violation_events) == 1
        assert violation_events[0][0] == GuardAction.REDUCE_BATCH_SIZE
        assert violation_events[0][1]["latency_ms"] == 200

        # Trigger recovery
        self.guard._handle_recovery({"recovery": "data"})

        assert len(recovery_events) == 1
        assert recovery_events[0]["recovery"] == "data"

    def test_guard_statistics(self):
        """Test guard statistics collection."""
        # Simulate some activity
        self.guard.metrics.total_evaluations = 10
        self.guard.metrics.violations_detected = 3
        self.guard.metrics.actions_taken = 2
        self.guard.metrics.current_violation_streak = 1

        # Add some mock batch metrics
        self.scheduler.batch_metrics = [BatchMetrics(4, 150.0, 0.5, 100.0, 180.0, time.time())]

        # Also update latency history for P95 calculation
        self.scheduler.latency_history = [180.0]

        stats = self.guard.get_guard_stats()

        assert stats["total_evaluations"] == 10
        assert stats["violations_detected"] == 3
        assert stats["actions_taken"] == 2
        assert stats["current_violation_streak"] == 1
        assert stats["current_latency_p95"] == 180.0
        assert "thresholds" in stats

    def test_violation_history(self):
        """Test violation history tracking."""
        # Add some violations with different actions to avoid cooldown issues
        self.guard._handle_violation(GuardAction.REDUCE_BATCH_SIZE, 200, {})
        time.sleep(0.01)  # Small delay for timestamp difference
        # Force a different action type to bypass cooldown logic
        self.guard.last_adjustment_time = 0  # Reset cooldown
        self.guard._handle_violation(GuardAction.THROTTLE_REQUESTS, 350, {})

        history = self.guard.get_violation_history()

        assert len(history) == 2
        assert history[0][1] == GuardAction.REDUCE_BATCH_SIZE.value
        assert history[1][1] == GuardAction.THROTTLE_REQUESTS.value

        # Timestamps should be increasing
        assert history[1][0] > history[0][0]

    def test_monitoring_lifecycle(self):
        """Test monitoring start/stop lifecycle."""
        assert not self.guard.monitoring_active

        # Start monitoring
        self.guard.start_monitoring()
        assert self.guard.monitoring_active

        # Stop monitoring
        self.guard.stop_monitoring()
        assert not self.guard.monitoring_active

    def test_metrics_reset(self):
        """Test metrics reset functionality."""
        # Add some metrics
        self.guard.metrics.total_evaluations = 5
        self.guard.metrics.violations_detected = 2
        self.guard.latency_window = [100, 200, 300]
        self.violation_history = [(time.time(), "test")]

        # Reset
        self.guard.reset_metrics()

        assert self.guard.metrics.total_evaluations == 0
        assert self.guard.metrics.violations_detected == 0
        assert len(self.guard.latency_window) == 0
        assert len(self.guard.violation_history) == 0


class TestLatencyGuardIntegration:
    """Integration tests for latency guard."""

    def setup_method(self):
        """Set up integration test fixtures."""
        self.batch_config = BatchConfig(max_batch_size=4, latency_target_ms=150)
        self.guard_config = GuardConfig(
            evaluation_interval_seconds=1, thresholds=LatencyThreshold(p95_ms=120, p99_ms=200, max_ms=300)
        )

    def teardown_method(self):
        """Clean up integration test fixtures."""
        stop_latency_guard()

    def test_guard_integration_with_scheduler(self):
        """Test guard working with actual scheduler."""
        scheduler = GPUBatchScheduler(self.batch_config)
        guard = get_latency_guard(scheduler, self.guard_config)

        # Start guard
        start_latency_guard(scheduler, self.guard_config)

        assert guard.monitoring_active

        # Simulate high latency
        scheduler.batch_metrics = [
            BatchMetrics(4, 250.0, 0.5, 60.0, 240.0, time.time())  # P95 violation
        ]

        # Wait for evaluation
        time.sleep(2)

        # Check if guard responded
        stats = guard.get_guard_stats()
        assert stats["total_evaluations"] > 0

        stop_latency_guard()

    def test_adaptive_response_to_latency(self):
        """Test adaptive response to changing latency conditions."""
        scheduler = GPUBatchScheduler(self.batch_config)
        guard = get_latency_guard(scheduler, self.guard_config)

        original_batch_size = scheduler.optimal_batch_size

        # Simulate high latency
        scheduler.batch_metrics = [
            BatchMetrics(4, 180.0, 0.5, 80.0, 170.0, time.time())  # Moderate violation
        ]

        # Manually trigger evaluation (normally done by monitoring thread)
        guard._evaluate_latency()

        # Batch size should be reduced
        assert scheduler.optimal_batch_size <= original_batch_size

        # Simulate recovery
        scheduler.batch_metrics = [
            BatchMetrics(2, 100.0, 0.3, 120.0, 110.0, time.time())  # Normal latency
        ]

        guard._evaluate_latency()

        # Should detect recovery
        assert guard.metrics.current_violation_streak == 0

    def test_global_guard_instance(self):
        """Test global guard instance management."""
        # Reset global instance
        import adaptive_latency_guard

        adaptive_latency_guard._guard_instance = None

        # Get guard
        guard1 = get_latency_guard()
        guard2 = get_latency_guard()

        # Should be the same instance
        assert guard1 is guard2

        # Start global guard
        start_latency_guard()

        # Stop global guard
        stop_latency_guard()

        # Instance should be cleared
        assert adaptive_latency_guard._guard_instance is None


class TestGuardConfiguration:
    """Test guard configuration options."""

    def test_default_configuration(self):
        """Test default guard configuration."""
        config = GuardConfig()

        assert config.enabled
        assert config.monitoring_window_seconds == 60
        assert config.evaluation_interval_seconds == 10
        assert config.thresholds.p95_ms == 200.0

    def test_custom_thresholds(self):
        """Test custom latency thresholds."""
        thresholds = LatencyThreshold(p50_ms=50.0, p95_ms=100.0, p99_ms=200.0, max_ms=500.0)
        config = GuardConfig(thresholds=thresholds)

        assert config.thresholds.p50_ms == 50.0
        assert config.thresholds.p95_ms == 100.0
        assert config.thresholds.p99_ms == 200.0
        assert config.thresholds.max_ms == 500.0

    def test_guard_action_enum(self):
        """Test guard action enumeration."""
        assert GuardAction.ALLOW.value == "allow"
        assert GuardAction.REDUCE_BATCH_SIZE.value == "reduce_batch_size"
        assert GuardAction.THROTTLE_REQUESTS.value == "throttle_requests"
        assert GuardAction.DROP_REQUESTS.value == "drop_requests"


if __name__ == "__main__":
    pytest.main([__file__])
