#!/usr/bin/env python3
"""
Tests for AGP Session FSM Implementation
"""

import asyncio
import time

import pytest

from router_service.agp_session_fsm import AGPEvent, AGPSessionConfig, AGPSessionFSM, AGPSessionManager, AGPSessionState


class TestAGPSessionFSM:
    """Test cases for AGP Session FSM."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = AGPSessionConfig(peer_address="192.168.1.100:179", peer_router_id="router-2", peer_adn=65001)
        self.fsm = AGPSessionFSM(self.config)

    def test_initial_state(self):
        """Test initial state is IDLE."""
        assert self.fsm.state == AGPSessionState.IDLE

    def test_state_transitions_from_idle(self):
        """Test state transitions from IDLE state."""
        # IDLE -> CONNECT on START
        self.fsm.handle_event(AGPEvent.START)
        assert self.fsm.state == AGPSessionState.CONNECT

    def test_state_transitions_from_connect(self):
        """Test state transitions from CONNECT state."""
        self.fsm._change_state(AGPSessionState.CONNECT)

        # CONNECT -> OPEN_SENT on CONNECT_SUCCESS
        self.fsm.handle_event(AGPEvent.CONNECT_SUCCESS)
        assert self.fsm.state == AGPSessionState.OPEN_SENT

        # Reset to CONNECT
        self.fsm._change_state(AGPSessionState.CONNECT)

        # CONNECT -> IDLE on CONNECT_FAIL
        self.fsm.handle_event(AGPEvent.CONNECT_FAIL)
        assert self.fsm.state == AGPSessionState.IDLE

        # Reset to CONNECT
        self.fsm._change_state(AGPSessionState.CONNECT)

        # CONNECT -> IDLE on TIMEOUT
        self.fsm.handle_event(AGPEvent.TIMEOUT)
        assert self.fsm.state == AGPSessionState.IDLE

    def test_state_transitions_from_open_sent(self):
        """Test state transitions from OPEN_SENT state."""
        self.fsm._change_state(AGPSessionState.OPEN_SENT)

        # OPEN_SENT -> OPEN_CONFIRMED on OPEN_RECEIVED
        self.fsm.handle_event(AGPEvent.OPEN_RECEIVED)
        assert self.fsm.state == AGPSessionState.OPEN_CONFIRMED

        # Reset to OPEN_SENT
        self.fsm._change_state(AGPSessionState.OPEN_SENT)

        # OPEN_SENT -> IDLE on ERROR
        self.fsm.handle_event(AGPEvent.ERROR)
        assert self.fsm.state == AGPSessionState.IDLE

        # Reset to OPEN_SENT
        self.fsm._change_state(AGPSessionState.OPEN_SENT)

        # OPEN_SENT -> IDLE on TIMEOUT
        self.fsm.handle_event(AGPEvent.TIMEOUT)
        assert self.fsm.state == AGPSessionState.IDLE

    def test_state_transitions_from_open_confirmed(self):
        """Test state transitions from OPEN_CONFIRMED state."""
        self.fsm._change_state(AGPSessionState.OPEN_CONFIRMED)

        # OPEN_CONFIRMED -> ESTABLISHED on KEEPALIVE_RECEIVED
        self.fsm.handle_event(AGPEvent.KEEPALIVE_RECEIVED)
        assert self.fsm.state == AGPSessionState.ESTABLISHED

        # Reset to OPEN_CONFIRMED
        self.fsm._change_state(AGPSessionState.OPEN_CONFIRMED)

        # OPEN_CONFIRMED -> IDLE on ERROR
        self.fsm.handle_event(AGPEvent.ERROR)
        assert self.fsm.state == AGPSessionState.IDLE

        # Reset to OPEN_CONFIRMED
        self.fsm._change_state(AGPSessionState.OPEN_CONFIRMED)

        # OPEN_CONFIRMED -> IDLE on TIMEOUT
        self.fsm.handle_event(AGPEvent.TIMEOUT)
        assert self.fsm.state == AGPSessionState.IDLE

    def test_state_transitions_from_established(self):
        """Test state transitions from ESTABLISHED state."""
        self.fsm._change_state(AGPSessionState.ESTABLISHED)

        # ESTABLISHED -> ESTABLISHED on KEEPALIVE_RECEIVED (stays established)
        self.fsm.handle_event(AGPEvent.KEEPALIVE_RECEIVED)
        assert self.fsm.state == AGPSessionState.ESTABLISHED

        # ESTABLISHED -> ESTABLISHED on UPDATE_RECEIVED (stays established)
        self.fsm.handle_event(AGPEvent.UPDATE_RECEIVED)
        assert self.fsm.state == AGPSessionState.ESTABLISHED

        # ESTABLISHED -> IDLE on ERROR
        self.fsm.handle_event(AGPEvent.ERROR)
        assert self.fsm.state == AGPSessionState.IDLE

        # Reset to ESTABLISHED
        self.fsm._change_state(AGPSessionState.ESTABLISHED)

        # ESTABLISHED -> IDLE on TIMEOUT
        self.fsm.handle_event(AGPEvent.TIMEOUT)
        assert self.fsm.state == AGPSessionState.IDLE

    def test_stop_event_from_any_state(self):
        """Test STOP event transitions to IDLE from any state."""
        states = [
            AGPSessionState.IDLE,
            AGPSessionState.CONNECT,
            AGPSessionState.OPEN_SENT,
            AGPSessionState.OPEN_CONFIRMED,
            AGPSessionState.ESTABLISHED,
        ]

        for state in states:
            self.fsm._change_state(state)
            self.fsm.handle_event(AGPEvent.STOP)
            assert self.fsm.state == AGPSessionState.IDLE

    def test_keepalive_timeout(self):
        """Test keepalive timeout detection."""
        self.fsm._change_state(AGPSessionState.ESTABLISHED)
        self.fsm.last_keepalive_received = time.time() - 40.0  # Past timeout

        # Mock the handle_event to capture the timeout event
        original_handle_event = self.fsm.handle_event
        timeout_called = False

        def mock_handle_event(event):
            nonlocal timeout_called
            if event == AGPEvent.TIMEOUT:
                timeout_called = True
            return original_handle_event(event)

        self.fsm.handle_event = mock_handle_event

        self.fsm.check_keepalive_timeout()
        assert timeout_called

    def test_send_keepalive(self):
        """Test sending keepalive messages."""
        self.fsm._change_state(AGPSessionState.OPEN_CONFIRMED)

        # Mock event trigger
        events_triggered = []
        original_trigger = self.fsm._trigger_event

        def mock_trigger(event, *args, **kwargs):
            events_triggered.append(event)
            return original_trigger(event, *args, **kwargs)

        self.fsm._trigger_event = mock_trigger

        self.fsm.send_keepalive()
        assert AGPEvent.KEEPALIVE_SENT in events_triggered
        assert self.fsm.last_keepalive_sent > 0

    def test_event_handlers(self):
        """Test event handler registration and triggering."""
        handler_called = False
        event_data = None

        def test_handler(data=None):
            nonlocal handler_called, event_data
            handler_called = True
            event_data = data

        self.fsm.register_handler(AGPEvent.START, test_handler)
        self.fsm._trigger_event(AGPEvent.START, "test_data")

        assert handler_called
        assert event_data == "test_data"

    def test_session_info(self):
        """Test session information retrieval."""
        info = self.fsm.get_session_info()

        expected_keys = [
            "state",
            "peer_address",
            "peer_router_id",
            "peer_adn",
            "last_keepalive_received",
            "last_keepalive_sent",
            "keepalive_misses",
            "session_uptime",
        ]

        for key in expected_keys:
            assert key in info

        assert info["state"] == AGPSessionState.IDLE.value
        assert info["peer_address"] == self.config.peer_address
        assert info["peer_router_id"] == self.config.peer_router_id
        assert info["peer_adn"] == self.config.peer_adn


class TestAGPSessionManager:
    """Test cases for AGP Session Manager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = AGPSessionManager()
        self.config1 = AGPSessionConfig(peer_address="192.168.1.100:179", peer_router_id="router-2", peer_adn=65001)
        self.config2 = AGPSessionConfig(peer_address="192.168.1.101:179", peer_router_id="router-3", peer_adn=65002)

    def test_add_session(self):
        """Test adding sessions."""
        session = self.manager.add_session("router-2", self.config1)
        assert isinstance(session, AGPSessionFSM)
        assert self.manager.get_session("router-2") is session

    def test_add_duplicate_session_raises_error(self):
        """Test adding duplicate session raises error."""
        self.manager.add_session("router-2", self.config1)

        with pytest.raises(ValueError, match="Session for peer router-2 already exists"):
            self.manager.add_session("router-2", self.config1)

    def test_remove_session(self):
        """Test removing sessions."""
        self.manager.add_session("router-2", self.config1)
        assert self.manager.get_session("router-2") is not None

        self.manager.remove_session("router-2")
        assert self.manager.get_session("router-2") is None

    def test_get_nonexistent_session(self):
        """Test getting nonexistent session returns None."""
        assert self.manager.get_session("nonexistent") is None

    def test_get_all_sessions_info(self):
        """Test getting information about all sessions."""
        self.manager.add_session("router-2", self.config1)
        self.manager.add_session("router-3", self.config2)

        info = self.manager.get_all_sessions_info()

        assert "router-2" in info
        assert "router-3" in info
        assert info["router-2"]["peer_router_id"] == "router-2"
        assert info["router-3"]["peer_router_id"] == "router-3"

    @pytest.mark.asyncio
    async def test_keepalive_monitor(self):
        """Test keepalive monitoring task."""
        self.manager.add_session("router-2", self.config1)
        session = self.manager.get_session("router-2")

        # Start monitoring
        self.manager.start_keepalive_monitor()
        assert self.manager.keepalive_task is not None

        # Put session in established state with old keepalive
        session._change_state(AGPSessionState.ESTABLISHED)
        session.last_keepalive_received = time.time() - 40.0

        # Wait for monitor to check
        await asyncio.sleep(2.0)

        # Session should have timed out and gone to IDLE
        assert session.state == AGPSessionState.IDLE

        # Stop monitoring
        self.manager.stop_keepalive_monitor()
        assert self.manager.keepalive_task is None


if __name__ == "__main__":
    pytest.main([__file__])
