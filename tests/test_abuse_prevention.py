"""
Comprehensive Tests for Advanced Loop Detection and Abuse Prevention System

Tests cover:
- CircuitBreaker functionality and state transitions
- RateLimiter with progressive tiers and violations
- LoopDetector for request loops and depth checking
- AnomalyDetector for behavior pattern analysis
- AbusePreventionSystem integration
"""

import os
import sys
import time
from datetime import datetime, timedelta

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "router_service"))

from abuse_prevention import (
    AbuseEvent,
    AbusePreventionSystem,
    AnomalyDetector,
    BlockReason,
    CircuitBreaker,
    LoopDetector,
    RateLimiter,
    RequestContext,
    RequestSignature,
    ThreatLevel,
)


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1, half_open_max_calls=2)

    def test_initial_state_is_closed(self):
        """Circuit breaker should start in closed state."""
        assert self.cb.state == "closed"
        assert self.cb.failure_count == 0

    def test_successful_call_in_closed_state(self):
        """Successful calls should work in closed state."""

        def success_func():
            return "success"

        result = self.cb.call(success_func)
        assert result == "success"
        assert self.cb.state == "closed"
        assert self.cb.failure_count == 0

    def test_failed_call_increments_failure_count(self):
        """Failed calls should increment failure count."""

        def failing_func():
            raise ValueError("test error")

        with pytest.raises(ValueError):
            self.cb.call(failing_func)

        assert self.cb.failure_count == 1
        assert self.cb.state == "closed"

    def test_circuit_opens_after_threshold_failures(self):
        """Circuit should open after reaching failure threshold."""

        def failing_func():
            raise ValueError("test error")

        # Fail enough times to open circuit
        for _ in range(3):
            with pytest.raises(ValueError):
                self.cb.call(failing_func)

        assert self.cb.state == "open"
        assert self.cb.failure_count == 3

    def test_open_circuit_rejects_calls(self):
        """Open circuit should reject calls immediately."""

        def failing_func():
            raise ValueError("test error")

        # Open the circuit
        for _ in range(3):
            with pytest.raises(ValueError):
                self.cb.call(failing_func)

        # Subsequent call should be rejected
        with pytest.raises(Exception) as exc_info:
            self.cb.call(lambda: "should not run")

        assert "Circuit breaker is open" in str(exc_info.value)

    def test_circuit_transitions_to_half_open_after_timeout(self):
        """Circuit should transition to half-open after recovery timeout."""

        def failing_func():
            raise ValueError("test error")

        # Open the circuit
        for _ in range(3):
            with pytest.raises(ValueError):
                self.cb.call(failing_func)

        assert self.cb.state == "open"

        # Wait for recovery timeout
        time.sleep(1.1)

        # Next call should transition to half-open
        def success_func():
            return "success"

        result = self.cb.call(success_func)
        assert result == "success"
        assert self.cb.state == "closed"  # Successful call closes it

    def test_half_open_state_limits_calls(self):
        """Half-open state should limit number of calls."""

        def failing_func():
            raise ValueError("test error")

        # Open the circuit
        for _ in range(3):
            with pytest.raises(ValueError):
                self.cb.call(failing_func)

        # Wait for recovery timeout
        time.sleep(1.1)

        # Make successful calls in half-open state
        self.cb._should_attempt_reset()  # Force half-open
        self.cb.state = "half_open"
        self.cb.half_open_calls = 0

        def success_func():
            return "success"

        # First calls should succeed
        self.cb.call(success_func)
        self.cb.call(success_func)

        # Should exceed half-open limit
        with pytest.raises(Exception) as exc_info:
            self.cb.call(success_func)

        assert "half-open limit exceeded" in str(exc_info.value)

    def test_successful_call_resets_failure_count(self):
        """Successful call should reset failure count."""

        def failing_func():
            raise ValueError("test error")

        def success_func():
            return "success"

        # Some failures
        with pytest.raises(ValueError):
            self.cb.call(failing_func)

        assert self.cb.failure_count == 1

        # Successful call resets
        self.cb.call(success_func)
        assert self.cb.failure_count == 0

    def test_custom_thresholds(self):
        """Circuit breaker should respect custom thresholds."""
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=2, half_open_max_calls=1)

        def failing_func():
            raise ValueError("test error")

        # Should not open before threshold
        for _ in range(4):
            with pytest.raises(ValueError):
                cb.call(failing_func)

        assert cb.state == "closed"

        # Should open at threshold
        with pytest.raises(ValueError):
            cb.call(failing_func)

        assert cb.state == "open"


class TestRateLimiter:
    """Test rate limiter functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.limiter = RateLimiter()

    def test_initial_requests_allowed(self):
        """Initial requests should be allowed."""
        allowed, reason, wait_time = self.limiter.is_allowed("tenant1", "user1", "endpoint1")
        assert allowed is True
        assert reason == "allowed"
        assert wait_time == 0

    def test_normal_tier_rate_limit(self):
        """Normal tier should enforce 1000 req/min limit."""
        tenant_id = "tenant1"
        user_id = "user1"
        endpoint = "endpoint1"

        # Make requests up to limit
        for _ in range(1000):
            allowed, _, _ = self.limiter.is_allowed(tenant_id, user_id, endpoint)
            assert allowed is True

        # Next request should be rejected
        allowed, reason, wait_time = self.limiter.is_allowed(tenant_id, user_id, endpoint)
        assert allowed is False
        assert "rate_limit_exceeded" in reason
        assert wait_time == 60

    def test_violation_escalates_tier(self):
        """Violations should escalate to higher tiers."""
        tenant_id = "tenant1"
        user_id = "user1"
        endpoint = "endpoint1"

        # Trigger violations by exceeding normal limit multiple times
        for violation_round in range(5):
            # Exceed limit to trigger violation
            for _ in range(1001):
                self.limiter.is_allowed(tenant_id, user_id, endpoint)

            # Wait to reset time window
            time.sleep(0.1)

        # Check tier escalation
        key = f"{tenant_id}:{user_id}:{endpoint}"
        tier = self.limiter.current_tier[tenant_id][key]
        assert tier == "elevated"

    def test_elevated_tier_has_lower_limit(self):
        """Elevated tier should have lower rate limit."""
        tenant_id = "tenant1"
        user_id = "user1"
        endpoint = "endpoint1"
        key = f"{tenant_id}:{user_id}:{endpoint}"

        # Force to elevated tier
        self.limiter.current_tier[tenant_id][key] = "elevated"

        # Elevated tier has 500 req/min limit
        for _ in range(500):
            allowed, _, _ = self.limiter.is_allowed(tenant_id, user_id, endpoint)
            assert allowed is True

        # Next should be rejected
        allowed, reason, _ = self.limiter.is_allowed(tenant_id, user_id, endpoint)
        assert allowed is False
        assert "elevated" in reason

    def test_blocked_tier_blocks_for_duration(self):
        """Blocked tier should block requests for duration."""
        tenant_id = "tenant1"
        user_id = "user1"
        endpoint = "endpoint1"
        key = f"{tenant_id}:{user_id}:{endpoint}"

        # Force to blocked state
        self.limiter.current_tier[tenant_id][key] = "blocked"
        self.limiter.blocked_until[tenant_id][key] = time.time() + 2

        # Should be blocked
        allowed, reason, remaining = self.limiter.is_allowed(tenant_id, user_id, endpoint)
        assert allowed is False
        assert reason == "temporarily_blocked"
        assert remaining > 0

    def test_reset_violations(self):
        """Reset should clear violations and restore normal tier."""
        tenant_id = "tenant1"
        user_id = "user1"
        endpoint = "endpoint1"
        key = f"{tenant_id}:{user_id}:{endpoint}"

        # Create some violations
        self.limiter.violation_counts[tenant_id][key] = 10
        self.limiter.current_tier[tenant_id][key] = "restricted"

        # Reset
        self.limiter.reset_violations(tenant_id, user_id, endpoint)

        # Verify reset
        assert self.limiter.violation_counts[tenant_id][key] == 0
        assert self.limiter.current_tier[tenant_id][key] == "normal"

    def test_different_endpoints_tracked_separately(self):
        """Different endpoints should have separate limits."""
        tenant_id = "tenant1"
        user_id = "user1"

        # Max out endpoint1
        for _ in range(1000):
            self.limiter.is_allowed(tenant_id, user_id, "endpoint1")

        # endpoint1 should be limited
        allowed, _, _ = self.limiter.is_allowed(tenant_id, user_id, "endpoint1")
        assert allowed is False

        # endpoint2 should still be allowed
        allowed, _, _ = self.limiter.is_allowed(tenant_id, user_id, "endpoint2")
        assert allowed is True

    def test_anonymous_users_tracked_separately(self):
        """Anonymous users should be tracked separately."""
        tenant_id = "tenant1"

        # Max out anonymous user
        for _ in range(1000):
            self.limiter.is_allowed(tenant_id, None, "endpoint1")

        # Anonymous should be limited
        allowed, _, _ = self.limiter.is_allowed(tenant_id, None, "endpoint1")
        assert allowed is False

        # Named user should still be allowed
        allowed, _, _ = self.limiter.is_allowed(tenant_id, "user1", "endpoint1")
        assert allowed is True

    def test_old_requests_cleaned_up(self):
        """Old requests should be cleaned from history."""
        tenant_id = "tenant1"
        user_id = "user1"
        endpoint = "endpoint1"
        key = f"{tenant_id}:{user_id}:{endpoint}"

        # Add some old requests
        old_time = time.time() - 120  # 2 minutes ago
        self.limiter.request_times[tenant_id][key].append(old_time)
        self.limiter.request_times[tenant_id][key].append(old_time)

        # Make new request
        self.limiter.is_allowed(tenant_id, user_id, endpoint)

        # Old requests should be cleaned
        times = list(self.limiter.request_times[tenant_id][key])
        assert all(time.time() - t < 120 for t in times)


class TestLoopDetector:
    """Test loop detector functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.detector = LoopDetector(max_depth=5, loop_window=300)

    def test_first_request_allowed(self):
        """First request should always be allowed."""
        signature = RequestSignature(
            content_hash="hash1", endpoint="/test", method="POST", tenant_id="tenant1", user_id="user1"
        )
        context = RequestContext(request_id="req1", signature=signature, timestamp=datetime.now())

        allowed, reason = self.detector.start_request(context)
        assert allowed is True
        assert reason is None

    def test_excessive_depth_rejected(self):
        """Requests exceeding max depth should be rejected."""
        signature = RequestSignature(
            content_hash="hash1", endpoint="/test", method="POST", tenant_id="tenant1", user_id="user1"
        )
        context = RequestContext(request_id="req1", signature=signature, timestamp=datetime.now(), depth=10)

        allowed, reason = self.detector.start_request(context)
        assert allowed is False
        assert "depth" in reason.lower()

    def test_immediate_loop_detected(self):
        """Immediate loop (same signature active) should be detected."""
        signature = RequestSignature(
            content_hash="hash1", endpoint="/test", method="POST", tenant_id="tenant1", user_id="user1"
        )

        # Start first request
        context1 = RequestContext(request_id="req1", signature=signature, timestamp=datetime.now())
        allowed, _ = self.detector.start_request(context1)
        assert allowed is True

        # Try to start duplicate
        context2 = RequestContext(request_id="req2", signature=signature, timestamp=datetime.now())
        allowed, reason = self.detector.start_request(context2)
        assert allowed is False
        assert "immediate loop" in reason.lower()

    def test_pattern_loop_detected(self):
        """Pattern loop (signature repeated 5+ times) should be detected."""
        signature = RequestSignature(
            content_hash="hash1", endpoint="/test", method="POST", tenant_id="tenant1", user_id="user1"
        )

        # Make 5 requests with same signature
        for i in range(5):
            context = RequestContext(request_id=f"req{i}", signature=signature, timestamp=datetime.now())
            self.detector.start_request(context)
            self.detector.end_request(f"req{i}")
            time.sleep(0.01)  # Small delay

        # 6th request should be rejected
        context = RequestContext(request_id="req5", signature=signature, timestamp=datetime.now())
        allowed, reason = self.detector.start_request(context)
        assert allowed is False
        assert "pattern loop" in reason.lower()

    def test_end_request_removes_from_active(self):
        """Ending request should remove it from active requests."""
        signature = RequestSignature(
            content_hash="hash1", endpoint="/test", method="POST", tenant_id="tenant1", user_id="user1"
        )
        context = RequestContext(request_id="req1", signature=signature, timestamp=datetime.now())

        self.detector.start_request(context)
        assert "req1" in self.detector.active_requests

        self.detector.end_request("req1")
        assert "req1" not in self.detector.active_requests

    def test_different_signatures_allowed_concurrently(self):
        """Different request signatures should be allowed concurrently."""
        sig1 = RequestSignature(
            content_hash="hash1", endpoint="/test1", method="POST", tenant_id="tenant1", user_id="user1"
        )
        sig2 = RequestSignature(
            content_hash="hash2", endpoint="/test2", method="POST", tenant_id="tenant1", user_id="user1"
        )

        ctx1 = RequestContext(request_id="req1", signature=sig1, timestamp=datetime.now())
        ctx2 = RequestContext(request_id="req2", signature=sig2, timestamp=datetime.now())

        allowed1, _ = self.detector.start_request(ctx1)
        allowed2, _ = self.detector.start_request(ctx2)

        assert allowed1 is True
        assert allowed2 is True

    def test_cleanup_removes_old_history(self):
        """Cleanup should remove old request history."""
        signature = RequestSignature(
            content_hash="hash1", endpoint="/test", method="POST", tenant_id="tenant1", user_id="user1"
        )

        # Create old request
        old_context = RequestContext(
            request_id="req_old", signature=signature, timestamp=datetime.now() - timedelta(seconds=1000)
        )
        self.detector.request_history[signature.tenant_id].append(old_context)

        # Create recent request
        recent_context = RequestContext(request_id="req_recent", signature=signature, timestamp=datetime.now())
        self.detector.request_history[signature.tenant_id].append(recent_context)

        # Run cleanup
        self.detector.cleanup_old_history()

        # Old should be removed, recent should remain
        history = self.detector.request_history[signature.tenant_id]
        assert len(history) == 1
        assert history[0].request_id == "req_recent"

    def test_depth_boundary_conditions(self):
        """Test depth at boundary of max depth."""
        signature = RequestSignature(
            content_hash="hash1", endpoint="/test", method="POST", tenant_id="tenant1", user_id="user1"
        )

        # At max depth should be allowed
        context_at_max = RequestContext(request_id="req1", signature=signature, timestamp=datetime.now(), depth=5)
        allowed, _ = self.detector.start_request(context_at_max)
        assert allowed is True

        # Clean up
        self.detector.end_request("req1")

        # Over max depth should be rejected
        context_over_max = RequestContext(request_id="req2", signature=signature, timestamp=datetime.now(), depth=6)
        allowed, _ = self.detector.start_request(context_over_max)
        assert allowed is False


class TestAnomalyDetector:
    """Test anomaly detector functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.detector = AnomalyDetector()

    def test_initial_analysis_not_anomalous(self):
        """Initial request should not be anomalous."""
        signature = RequestSignature(
            content_hash="hash1", endpoint="/test", method="POST", tenant_id="tenant1", user_id="user1"
        )
        context = RequestContext(request_id="req1", signature=signature, timestamp=datetime.now())

        is_anomalous, score, reason = self.detector.analyze_request(context)
        assert is_anomalous is False
        assert score < 0.8

    def test_high_frequency_detected(self):
        """High request frequency should increase anomaly score."""
        signature = RequestSignature(
            content_hash="hash1", endpoint="/test", method="POST", tenant_id="tenant1", user_id="user1"
        )

        # Simulate many requests
        for i in range(150):
            context = RequestContext(request_id=f"req{i}", signature=signature, timestamp=datetime.now())
            self.detector.analyze_request(context)

        # Latest should have higher score
        context = RequestContext(request_id="req_final", signature=signature, timestamp=datetime.now())
        is_anomalous, score, reason = self.detector.analyze_request(context)

        assert score > 0.2  # Should have some score for frequency
        assert "frequency" in reason.lower() or "request" in reason.lower()

    def test_endpoint_diversity_detected(self):
        """Accessing many different endpoints should increase score."""
        tenant_id = "tenant1"
        user_id = "user1"

        # Access many different endpoints
        for i in range(25):
            signature = RequestSignature(
                content_hash=f"hash{i}", endpoint=f"/endpoint{i}", method="POST", tenant_id=tenant_id, user_id=user_id
            )
            context = RequestContext(request_id=f"req{i}", signature=signature, timestamp=datetime.now())
            self.detector.analyze_request(context)

        # Check anomaly score
        score = self.detector.anomaly_scores[tenant_id]
        assert score > 0.2  # Should detect endpoint scanning

    def test_deep_recursion_detected(self):
        """High average request depth should increase score."""
        signature = RequestSignature(
            content_hash="hash1", endpoint="/test", method="POST", tenant_id="tenant1", user_id="user1"
        )

        # Make requests with high depth
        for i in range(10):
            context = RequestContext(request_id=f"req{i}", signature=signature, timestamp=datetime.now(), depth=8)
            self.detector.analyze_request(context)

        # Check anomaly score
        score = self.detector.anomaly_scores["tenant1"]
        assert score > 0.2  # Should detect deep recursion

    def test_anomaly_score_calculation(self):
        """Test internal anomaly score calculation."""
        tenant_id = "tenant1"
        patterns = {
            "timestamps": [time.time() for _ in range(150)],
            "endpoints": [f"/endpoint{i % 25}" for i in range(150)],
            "methods": ["POST"] * 150,
            "depths": [7] * 150,
        }

        score = self.detector._calculate_anomaly_score(tenant_id, patterns)

        # Should have components from frequency, endpoints, and depth
        assert score > 0.5  # Combined should be significant

    def test_entropy_calculation(self):
        """Test entropy calculation for distributions."""
        # Uniform distribution should have high entropy
        uniform_values = [10, 10, 10, 10]
        uniform_entropy = self.detector._calculate_entropy(uniform_values)

        # Skewed distribution should have lower entropy
        skewed_values = [100, 1, 1, 1]
        skewed_entropy = self.detector._calculate_entropy(skewed_values)

        assert uniform_entropy > skewed_entropy

    def test_old_patterns_cleaned_up(self):
        """Old patterns should be cleaned from analysis."""
        signature = RequestSignature(
            content_hash="hash1", endpoint="/test", method="POST", tenant_id="tenant1", user_id="user1"
        )

        # Add old timestamp
        self.detector.request_patterns["tenant1"]["timestamps"].append(time.time() - 700)

        # Add new request
        context = RequestContext(request_id="req1", signature=signature, timestamp=datetime.now())
        self.detector.analyze_request(context)

        # Old timestamps should be cleaned
        timestamps = self.detector.request_patterns["tenant1"]["timestamps"]
        assert all(time.time() - t < 600 for t in timestamps)

    def test_empty_patterns_return_zero_score(self):
        """Empty patterns should return zero anomaly score."""
        score = self.detector._calculate_anomaly_score("tenant_empty", {"timestamps": []})
        assert score == 0.0


class TestAbusePreventionSystem:
    """Test integrated abuse prevention system."""

    def setup_method(self):
        """Set up test fixtures."""
        self.system = AbusePreventionSystem()

    def test_check_request_allows_normal_request(self):
        """Normal requests should be allowed."""
        allowed, block_reason, message = self.system.check_request(
            request_id="req1",
            tenant_id="tenant1",
            endpoint="/test",
            method="POST",
            content="test content",
            user_id="user1",
        )

        assert allowed is True
        assert block_reason is None
        assert "allowed" in message.lower()

    def test_check_request_blocks_rate_limit_exceeded(self):
        """Requests exceeding rate limit should be blocked."""
        tenant_id = "tenant1"
        user_id = "user1"
        endpoint = "/test"

        # Exhaust rate limit
        for i in range(1001):
            self.system.check_request(
                request_id=f"req{i}",
                tenant_id=tenant_id,
                endpoint=endpoint,
                method="POST",
                content=f"content{i}",
                user_id=user_id,
            )

        # Next should be blocked
        allowed, block_reason, message = self.system.check_request(
            request_id="req_blocked",
            tenant_id=tenant_id,
            endpoint=endpoint,
            method="POST",
            content="content",
            user_id=user_id,
        )

        assert allowed is False
        assert block_reason == BlockReason.RATE_LIMIT_EXCEEDED
        assert "rate limit" in message.lower()

    def test_check_request_blocks_request_loop(self):
        """Request loops should be blocked."""
        signature_data = {
            "tenant_id": "tenant1",
            "endpoint": "/test",
            "method": "POST",
            "content": "same content",
            "user_id": "user1",
        }

        # Start first request
        self.system.check_request(request_id="req1", **signature_data)

        # Try duplicate (should be blocked)
        allowed, block_reason, message = self.system.check_request(request_id="req2", **signature_data)

        assert allowed is False
        assert block_reason == BlockReason.REQUEST_LOOP
        assert "loop" in message.lower()

    def test_check_request_blocks_excessive_depth(self):
        """Requests with excessive depth should be blocked."""
        allowed, block_reason, message = self.system.check_request(
            request_id="req1",
            tenant_id="tenant1",
            endpoint="/test",
            method="POST",
            content="test",
            depth=20,
        )

        assert allowed is False
        assert block_reason == BlockReason.REQUEST_LOOP
        assert "depth" in message.lower()

    def test_check_request_detects_anomalous_behavior(self):
        """Anomalous behavior patterns should be detected."""
        tenant_id = "tenant1"
        user_id = "user1"

        # Create anomalous pattern - many requests to different endpoints
        for i in range(150):
            self.system.check_request(
                request_id=f"req{i}",
                tenant_id=tenant_id,
                endpoint=f"/endpoint{i % 25}",
                method="POST",
                content=f"content{i}",
                user_id=user_id,
            )

        # Should have detected anomaly
        events = self.system.get_abuse_events(tenant_id=tenant_id, hours=1)
        anomaly_events = [e for e in events if e.get("block_reason") == BlockReason.ANOMALOUS_BEHAVIOR.value]

        assert len(anomaly_events) > 0

    def test_end_request_removes_from_tracking(self):
        """Ending request should remove it from tracking."""
        self.system.check_request(
            request_id="req1", tenant_id="tenant1", endpoint="/test", method="POST", content="test"
        )

        assert "req1" in self.system.loop_detector.active_requests

        self.system.end_request("req1")
        assert "req1" not in self.system.loop_detector.active_requests

    def test_blocked_entity_prevents_requests(self):
        """Blocked entities should have all requests blocked."""
        tenant_id = "tenant1"
        user_id = "user1"

        # Block entity
        entity_key = f"{tenant_id}:{user_id}"
        self.system.blocked_entities[entity_key] = datetime.now() + timedelta(minutes=10)

        # Try to make request
        allowed, block_reason, message = self.system.check_request(
            request_id="req1", tenant_id=tenant_id, endpoint="/test", method="POST", content="test", user_id=user_id
        )

        assert allowed is False
        assert block_reason == BlockReason.SUSPICIOUS_PATTERN
        assert "blocked" in message.lower()

    def test_blocked_entity_unblocks_after_timeout(self):
        """Blocked entities should be unblocked after timeout."""
        tenant_id = "tenant1"
        user_id = "user1"

        # Block entity briefly
        entity_key = f"{tenant_id}:{user_id}"
        self.system.blocked_entities[entity_key] = datetime.now() + timedelta(milliseconds=100)

        # Wait for unblock
        time.sleep(0.15)

        # Should be allowed now
        allowed, _, _ = self.system.check_request(
            request_id="req1", tenant_id=tenant_id, endpoint="/test", method="POST", content="test", user_id=user_id
        )

        assert allowed is True
        assert entity_key not in self.system.blocked_entities

    def test_get_abuse_events_filters_by_tenant(self):
        """Getting abuse events should filter by tenant ID."""
        # Create events for different tenants
        for tenant_num in range(3):
            tenant_id = f"tenant{tenant_num}"
            # Exceed rate limit to create event
            for i in range(1001):
                self.system.check_request(
                    request_id=f"req{tenant_num}_{i}",
                    tenant_id=tenant_id,
                    endpoint="/test",
                    method="POST",
                    content=f"content{i}",
                )

        # Get events for specific tenant
        events = self.system.get_abuse_events(tenant_id="tenant1", hours=1)

        # Should only have events for tenant1
        assert all(e.get("tenant_id") == "tenant1" for e in events)

    def test_get_abuse_events_filters_by_time(self):
        """Getting abuse events should filter by time."""
        tenant_id = "tenant1"

        # Create old event
        old_event = AbuseEvent(
            event_id="old",
            timestamp=datetime.now() - timedelta(hours=25),
            tenant_id=tenant_id,
            user_id="user1",
            source_ip="1.2.3.4",
            block_reason=BlockReason.RATE_LIMIT_EXCEEDED,
            threat_level=ThreatLevel.MEDIUM,
            details={},
            action_taken="blocked",
        )
        self.system.abuse_events.append(old_event)

        # Get events from last 24 hours
        events = self.system.get_abuse_events(tenant_id=tenant_id, hours=24)

        # Should not include old event
        event_ids = [e.get("event_id") for e in events]
        assert "old" not in event_ids

    def test_get_system_status(self):
        """System status should provide overview metrics."""
        # Make some requests
        self.system.check_request(
            request_id="req1", tenant_id="tenant1", endpoint="/test", method="POST", content="test"
        )

        status = self.system.get_system_status()

        assert "active_requests" in status
        assert "circuit_breakers" in status
        assert "blocked_entities" in status
        assert "recent_abuse_events" in status
        assert "anomaly_scores" in status

    def test_reset_entity_clears_all_tracking(self):
        """Resetting entity should clear all tracking data."""
        tenant_id = "tenant1"
        user_id = "user1"
        entity_key = f"{tenant_id}:{user_id}"

        # Create tracking data
        self.system.blocked_entities[entity_key] = datetime.now() + timedelta(minutes=10)
        self.system.rate_limiter.violation_counts[tenant_id][f"{entity_key}:default"] = 10
        self.system.anomaly_detector.anomaly_scores[tenant_id] = 0.9

        # Reset
        self.system.reset_entity(tenant_id, user_id)

        # Verify all cleared
        assert entity_key not in self.system.blocked_entities
        assert self.system.rate_limiter.violation_counts[tenant_id][f"{entity_key}:default"] == 0
        assert tenant_id not in self.system.anomaly_detector.anomaly_scores

    def test_circuit_breaker_integration(self):
        """Circuit breakers should be tracked per tenant-endpoint."""
        tenant_id = "tenant1"
        endpoint = "/test"
        key = f"{tenant_id}:{endpoint}"

        # Get circuit breaker
        cb = self.system.circuit_breakers[key]
        assert isinstance(cb, CircuitBreaker)

        # Modify state
        cb.state = "open"

        # Should block request
        allowed, block_reason, message = self.system.check_request(
            request_id="req1", tenant_id=tenant_id, endpoint=endpoint, method="POST", content="test"
        )

        assert allowed is False
        assert block_reason == BlockReason.CIRCUIT_BREAKER_OPEN


class TestRequestSignature:
    """Test RequestSignature dataclass."""

    def test_signature_equality(self):
        """Signatures with same data should be equal."""
        sig1 = RequestSignature(
            content_hash="hash1", endpoint="/test", method="POST", tenant_id="tenant1", user_id="user1"
        )
        sig2 = RequestSignature(
            content_hash="hash1", endpoint="/test", method="POST", tenant_id="tenant1", user_id="user1"
        )

        assert sig1 == sig2

    def test_signature_hashable(self):
        """Signatures should be hashable for use in sets/dicts."""
        sig1 = RequestSignature(
            content_hash="hash1", endpoint="/test", method="POST", tenant_id="tenant1", user_id="user1"
        )
        sig2 = RequestSignature(
            content_hash="hash2", endpoint="/test", method="POST", tenant_id="tenant1", user_id="user1"
        )

        sig_set = {sig1, sig2}
        assert len(sig_set) == 2
        assert sig1 in sig_set

    def test_signature_with_none_user_id(self):
        """Signature should handle None user_id."""
        sig = RequestSignature(
            content_hash="hash1", endpoint="/test", method="POST", tenant_id="tenant1", user_id=None
        )

        assert sig.user_id is None
        assert hash(sig)  # Should be hashable


class TestRequestContext:
    """Test RequestContext dataclass."""

    def test_context_to_dict(self):
        """Context should serialize to dict."""
        signature = RequestSignature(
            content_hash="hash1", endpoint="/test", method="POST", tenant_id="tenant1", user_id="user1"
        )
        context = RequestContext(
            request_id="req1",
            signature=signature,
            timestamp=datetime.now(),
            parent_request_id="parent1",
            depth=5,
            source_ip="1.2.3.4",
            user_agent="test-agent",
        )

        data = context.to_dict()

        assert data["request_id"] == "req1"
        assert data["parent_request_id"] == "parent1"
        assert data["depth"] == 5
        assert data["source_ip"] == "1.2.3.4"
        assert data["user_agent"] == "test-agent"
        assert "signature" in data
        assert "timestamp" in data


class TestAbuseEvent:
    """Test AbuseEvent dataclass."""

    def test_event_to_dict(self):
        """Event should serialize to dict."""
        event = AbuseEvent(
            event_id="evt1",
            timestamp=datetime.now(),
            tenant_id="tenant1",
            user_id="user1",
            source_ip="1.2.3.4",
            block_reason=BlockReason.RATE_LIMIT_EXCEEDED,
            threat_level=ThreatLevel.HIGH,
            details={"key": "value"},
            action_taken="blocked",
        )

        data = event.to_dict()

        assert data["event_id"] == "evt1"
        assert data["tenant_id"] == "tenant1"
        assert data["user_id"] == "user1"
        assert data["source_ip"] == "1.2.3.4"
        assert data["block_reason"] == "rate_limit_exceeded"
        assert data["threat_level"] == "high"
        assert data["action_taken"] == "blocked"
        assert data["details"]["key"] == "value"


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_check_request_abuse_allowed(self):
        """check_request_abuse should return True for allowed requests."""
        from abuse_prevention import check_request_abuse

        allowed, message = check_request_abuse(
            request_id="req1", tenant_id="tenant1", endpoint="/test", method="POST", content="test content"
        )

        assert allowed is True
        assert message is None

    def test_check_request_abuse_blocked(self):
        """check_request_abuse should return False for blocked requests."""
        from abuse_prevention import check_request_abuse

        # Make requests with same signature (will cause loop)
        check_request_abuse(
            request_id="req1", tenant_id="tenant1", endpoint="/test", method="POST", content="same content"
        )

        allowed, message = check_request_abuse(
            request_id="req2", tenant_id="tenant1", endpoint="/test", method="POST", content="same content"
        )

        assert allowed is False
        assert message is not None

    def test_end_request_tracking(self):
        """end_request_tracking should work without errors."""
        from abuse_prevention import end_request_tracking

        end_request_tracking("req1", success=True)
        end_request_tracking("req2", success=False)

        # Should not raise errors

    def test_get_abuse_statistics(self):
        """get_abuse_statistics should return stats dict."""
        from abuse_prevention import get_abuse_statistics

        stats = get_abuse_statistics(tenant_id="tenant1")

        assert "system_status" in stats
        assert "recent_events" in stats
        assert isinstance(stats["system_status"], dict)
        assert isinstance(stats["recent_events"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
