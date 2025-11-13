"""Tests for GAP-305: Consistency level enforcement (EVENTUAL vs RYW)."""

import time

import pytest

from router_service.consistency_enforcer import ConsistencyEnforcer, SessionState, get_enforcer, measure_ryw_latency


class TestConsistencyEnforcer:
    """Test the consistency enforcer functionality."""

    def test_session_creation(self):
        """Test session creation and state management."""
        enforcer = ConsistencyEnforcer()

        # Test EVENTUAL session
        session = enforcer.start_session("session1", "EVENTUAL", "tenant1")
        assert session.session_id == "session1"
        assert session.consistency_level == "EVENTUAL"
        assert session.namespace == "tenant1"
        assert not session.is_expired

        # Test RYW session
        session2 = enforcer.start_session("session2", "RYW", "tenant2")
        assert session2.consistency_level == "RYW"

    def test_write_recording(self):
        """Test write operation recording."""
        enforcer = ConsistencyEnforcer()
        session = enforcer.start_session("session1", "RYW", "tenant1")

        # Record a write
        enforcer.record_write("session1", "tenant1")

        # Check that write was recorded
        assert session.last_write_at is not None
        assert session.should_enforce_ryw

    def test_consistency_routing(self):
        """Test routing decisions based on consistency level."""
        enforcer = ConsistencyEnforcer()

        # EVENTUAL session should not route to primary
        enforcer.start_session("session1", "EVENTUAL", "tenant1")
        assert not enforcer.should_route_to_primary("session1", "tenant1")

        # RYW session without recent write should not route to primary
        enforcer.start_session("session2", "RYW", "tenant1")
        assert not enforcer.should_route_to_primary("session2", "tenant1")

        # RYW session with recent write should route to primary
        enforcer.record_write("session2", "tenant1")
        assert enforcer.should_route_to_primary("session2", "tenant1")

    def test_session_expiry(self):
        """Test session expiry handling."""
        enforcer = ConsistencyEnforcer()

        # Create session with short TTL
        session = enforcer.start_session("session1", "RYW", "tenant1", ttl_seconds=0.1)

        # Should not be expired immediately
        assert not session.is_expired

        # Wait for expiry
        time.sleep(0.2)
        assert session.is_expired

        # Should not enforce RYW for expired session
        assert not enforcer.should_route_to_primary("session1", "tenant1")

    def test_namespace_defaults(self):
        """Test namespace-level consistency defaults."""
        enforcer = ConsistencyEnforcer()

        # Set namespace default
        enforcer.set_namespace_default("secure_ns", "RYW")

        # Session without explicit level should use namespace default
        session = enforcer.start_session("session1", namespace="secure_ns")
        assert session.consistency_level == "RYW"

        # Explicit level should override namespace default
        session2 = enforcer.start_session("session2", "EVENTUAL", "secure_ns")
        assert session2.consistency_level == "EVENTUAL"

    def test_ryw_window_expiry(self):
        """Test that RYW enforcement expires after write window."""
        enforcer = ConsistencyEnforcer()
        enforcer.start_session("session1", "RYW", "tenant1")

        # Record write
        enforcer.record_write("session1", "tenant1")
        assert enforcer.should_route_to_primary("session1", "tenant1")

        # Wait for RYW window to expire (2 seconds in implementation)
        time.sleep(2.1)

        # Should no longer enforce RYW
        assert not enforcer.should_route_to_primary("session1", "tenant1")


class TestSessionState:
    """Test SessionState dataclass."""

    def test_session_state_creation(self):
        """Test SessionState creation and properties."""
        session = SessionState(
            session_id="test_session", consistency_level="RYW", created_at=time.time(), namespace="test_ns"
        )

        assert session.session_id == "test_session"
        assert session.consistency_level == "RYW"
        assert session.namespace == "test_ns"
        assert not session.is_expired
        assert not session.should_enforce_ryw  # No write recorded yet

    def test_ryw_enforcement_logic(self):
        """Test RYW enforcement logic."""
        session = SessionState(
            session_id="test_session", consistency_level="RYW", created_at=time.time(), namespace="test_ns"
        )

        # No write recorded
        assert not session.should_enforce_ryw

        # Record write
        session.last_write_at = time.time()
        assert session.should_enforce_ryw

        # EVENTUAL session should never enforce RYW
        session.consistency_level = "EVENTUAL"
        assert not session.should_enforce_ryw


def test_measure_ryw_latency():
    """Test the RYW latency measurement decorator."""

    @measure_ryw_latency
    def dummy_operation():
        time.sleep(0.01)
        return "result"

    result = dummy_operation()
    assert result == "result"


def test_get_enforcer():
    """Test global enforcer access."""
    enforcer = get_enforcer()
    assert isinstance(enforcer, ConsistencyEnforcer)

    # Should return the same instance
    enforcer2 = get_enforcer()
    assert enforcer is enforcer2


if __name__ == "__main__":
    pytest.main([__file__])
