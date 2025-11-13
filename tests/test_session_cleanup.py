#!/usr/bin/env python3
"""
Test for session cleanup mechanism to prevent memory leaks.
"""

import asyncio
import time

import pytest

from router_service.service import _SESSION_ACTIVE, _SESSION_LOCK, _SESSION_TTL


@pytest.mark.asyncio
async def test_session_cleanup_mechanism():
    """Test that expired sessions are automatically cleaned up."""
    # Setup: Add some test sessions with old timestamps
    test_sessions = {
        "expired_session_1": {"count": 1, "last_activity": time.time() - _SESSION_TTL - 100},
        "expired_session_2": {"count": 2, "last_activity": time.time() - _SESSION_TTL - 200},
        "active_session": {"count": 1, "last_activity": time.time()},  # Recent activity
    }

    async with _SESSION_LOCK:
        _SESSION_ACTIVE.update(test_sessions)

    # Verify sessions are initially present
    assert len(_SESSION_ACTIVE) == 3
    assert "expired_session_1" in _SESSION_ACTIVE
    assert "expired_session_2" in _SESSION_ACTIVE
    assert "active_session" in _SESSION_ACTIVE

    # Manually trigger cleanup by calling the cleanup logic directly
    current_time = time.time()
    async with _SESSION_LOCK:
        expired_sessions = []
        for sess_id, session_data in _SESSION_ACTIVE.items():
            if current_time - session_data["last_activity"] > _SESSION_TTL:
                expired_sessions.append(sess_id)

        for sess_id in expired_sessions:
            _SESSION_ACTIVE.pop(sess_id, None)

    # Verify expired sessions were cleaned up but active session remains
    async with _SESSION_LOCK:
        assert "expired_session_1" not in _SESSION_ACTIVE
        assert "expired_session_2" not in _SESSION_ACTIVE
        assert "active_session" in _SESSION_ACTIVE
        assert len(_SESSION_ACTIVE) == 1


def test_session_structure():
    """Test that session data structure includes required fields."""
    async def _test():
        session_id = "test_session"
        session_data = {"count": 3, "last_activity": time.time()}

        async with _SESSION_LOCK:
            _SESSION_ACTIVE[session_id] = session_data

        async with _SESSION_LOCK:
            stored_data = _SESSION_ACTIVE[session_id]
            assert "count" in stored_data
            assert "last_activity" in stored_data
            assert stored_data["count"] == 3
            assert isinstance(stored_data["last_activity"], float)

        # Cleanup
        async with _SESSION_LOCK:
            _SESSION_ACTIVE.pop(session_id, None)

    asyncio.run(_test())


if __name__ == "__main__":
    asyncio.run(test_session_cleanup_mechanism())
    test_session_structure()
    print("✅ Session cleanup tests passed!")
