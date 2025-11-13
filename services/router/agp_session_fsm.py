#!/usr/bin/env python3
"""
AGP Session FSM Implementation

Implements the AGP (Agent Gateway Protocol) session state machine for inter-router federation.
Based on BGP-inspired FSM with states: IDLE → CONNECT → OPEN_SENT → OPEN_CONFIRMED → ESTABLISHED.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from metrics.registry import REGISTRY


class AGPSessionState(Enum):
    """AGP session states."""

    IDLE = "idle"
    CONNECT = "connect"
    OPEN_SENT = "open_sent"
    OPEN_CONFIRMED = "open_confirmed"
    ESTABLISHED = "established"


class AGPEvent(Enum):
    """AGP session events."""

    START = "start"
    STOP = "stop"
    CONNECT_SUCCESS = "connect_success"
    CONNECT_FAIL = "connect_fail"
    OPEN_RECEIVED = "open_received"
    OPEN_SENT = "open_sent"
    KEEPALIVE_RECEIVED = "keepalive_received"
    KEEPALIVE_SENT = "keepalive_sent"
    UPDATE_RECEIVED = "update_received"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class AGPSessionConfig:
    """Configuration for AGP session."""

    peer_address: str
    peer_router_id: str
    peer_adn: int
    keepalive_interval: float = 10.0
    hold_time: float = 30.0
    connect_retry_time: float = 5.0
    max_keepalive_misses: int = 3


class AGPSessionFSM:
    """AGP Session Finite State Machine."""

    def __init__(self, config: AGPSessionConfig):
        self.config = config
        self.state = AGPSessionState.IDLE
        self.last_keepalive_sent = 0.0
        self.last_keepalive_received = 0.0
        self.keepalive_misses = 0
        self.connect_attempts = 0
        self.session_start_time = 0.0

        # Metrics
        self.sessions_established = REGISTRY.counter("agp_sessions_established_total")
        self.session_state_changes = REGISTRY.counter("agp_session_state_changes_total")
        self.keepalive_misses_total = REGISTRY.counter("agp_keepalive_misses_total")

        # Event handlers
        self.event_handlers: dict[AGPEvent, list[Callable]] = {}

    def register_handler(self, event: AGPEvent, handler: Callable) -> None:
        """Register an event handler."""
        if event not in self.event_handlers:
            self.event_handlers[event] = []
        self.event_handlers[event].append(handler)

    def _trigger_event(self, event: AGPEvent, *args, **kwargs) -> None:
        """Trigger event handlers."""
        if event in self.event_handlers:
            for handler in self.event_handlers[event]:
                try:
                    handler(*args, **kwargs)
                except Exception as e:
                    print(f"Event handler error for {event}: {e}")

    def _change_state(self, new_state: AGPSessionState) -> None:
        """Change session state and update metrics."""
        old_state = self.state
        self.state = new_state
        self.session_state_changes.inc()

        print(f"AGP Session state change: {old_state.value} -> {new_state.value}")

        if new_state == AGPSessionState.ESTABLISHED:
            self.sessions_established.inc()
            self.session_start_time = time.time()

    def handle_event(self, event: AGPEvent) -> None:
        """Handle an AGP event and transition state if needed."""
        current_state = self.state

        if current_state == AGPSessionState.IDLE:
            if event == AGPEvent.START:
                self._change_state(AGPSessionState.CONNECT)
                self._trigger_event(AGPEvent.START)

        elif current_state == AGPSessionState.CONNECT:
            if event == AGPEvent.CONNECT_SUCCESS:
                self._change_state(AGPSessionState.OPEN_SENT)
                self._trigger_event(AGPEvent.CONNECT_SUCCESS)
            elif event == AGPEvent.CONNECT_FAIL or event == AGPEvent.TIMEOUT:
                self._change_state(AGPSessionState.IDLE)
                self._trigger_event(event)

        elif current_state == AGPSessionState.OPEN_SENT:
            if event == AGPEvent.OPEN_RECEIVED:
                self._change_state(AGPSessionState.OPEN_CONFIRMED)
                self._trigger_event(AGPEvent.OPEN_RECEIVED)
            elif event == AGPEvent.ERROR or event == AGPEvent.TIMEOUT:
                self._change_state(AGPSessionState.IDLE)
                self._trigger_event(event)

        elif current_state == AGPSessionState.OPEN_CONFIRMED:
            if event == AGPEvent.KEEPALIVE_RECEIVED:
                self._change_state(AGPSessionState.ESTABLISHED)
                self.last_keepalive_received = time.time()
                self._trigger_event(AGPEvent.KEEPALIVE_RECEIVED)
            elif event == AGPEvent.ERROR or event == AGPEvent.TIMEOUT:
                self._change_state(AGPSessionState.IDLE)
                self._trigger_event(event)

        elif current_state == AGPSessionState.ESTABLISHED:
            if event == AGPEvent.KEEPALIVE_RECEIVED:
                self.last_keepalive_received = time.time()
                self.keepalive_misses = 0
                self._trigger_event(AGPEvent.KEEPALIVE_RECEIVED)
            elif event == AGPEvent.UPDATE_RECEIVED:
                self._trigger_event(AGPEvent.UPDATE_RECEIVED)
            elif event == AGPEvent.ERROR or event == AGPEvent.TIMEOUT:
                self._change_state(AGPSessionState.IDLE)
                self._trigger_event(event)

        # Handle STOP event from any state
        if event == AGPEvent.STOP:
            self._change_state(AGPSessionState.IDLE)
            self._trigger_event(AGPEvent.STOP)

    def check_keepalive_timeout(self) -> None:
        """Check for keepalive timeout and handle if needed."""
        if self.state == AGPSessionState.ESTABLISHED:
            now = time.time()
            time_since_last_keepalive = now - self.last_keepalive_received

            if time_since_last_keepalive > self.config.keepalive_interval * self.config.max_keepalive_misses:
                self.keepalive_misses_total.inc()
                print(f"AGP Session keepalive timeout: {time_since_last_keepalive:.1f}s")
                self.handle_event(AGPEvent.TIMEOUT)

    def send_keepalive(self) -> None:
        """Send a keepalive message."""
        if self.state in [AGPSessionState.OPEN_CONFIRMED, AGPSessionState.ESTABLISHED]:
            self.last_keepalive_sent = time.time()
            self._trigger_event(AGPEvent.KEEPALIVE_SENT)

    def get_session_info(self) -> dict[str, Any]:
        """Get current session information."""
        return {
            "state": self.state.value,
            "peer_address": self.config.peer_address,
            "peer_router_id": self.config.peer_router_id,
            "peer_adn": self.config.peer_adn,
            "last_keepalive_received": self.last_keepalive_received,
            "last_keepalive_sent": self.last_keepalive_sent,
            "keepalive_misses": self.keepalive_misses,
            "session_uptime": time.time() - self.session_start_time if self.session_start_time > 0 else 0,
        }


class AGPSessionManager:
    """Manages multiple AGP sessions."""

    def __init__(self):
        self.sessions: dict[str, AGPSessionFSM] = {}
        self.keepalive_task: asyncio.Task | None = None

    def add_session(self, peer_router_id: str, config: AGPSessionConfig) -> AGPSessionFSM:
        """Add a new AGP session."""
        if peer_router_id in self.sessions:
            raise ValueError(f"Session for peer {peer_router_id} already exists")

        session = AGPSessionFSM(config)
        self.sessions[peer_router_id] = session
        return session

    def remove_session(self, peer_router_id: str) -> None:
        """Remove an AGP session."""
        if peer_router_id in self.sessions:
            session = self.sessions[peer_router_id]
            session.handle_event(AGPEvent.STOP)
            del self.sessions[peer_router_id]

    def get_session(self, peer_router_id: str) -> AGPSessionFSM | None:
        """Get a session by peer router ID."""
        return self.sessions.get(peer_router_id)

    def start_keepalive_monitor(self) -> None:
        """Start the keepalive monitoring task."""
        if self.keepalive_task is None:
            self.keepalive_task = asyncio.create_task(self._keepalive_monitor())

    def stop_keepalive_monitor(self) -> None:
        """Stop the keepalive monitoring task."""
        if self.keepalive_task:
            self.keepalive_task.cancel()
            self.keepalive_task = None

    async def _keepalive_monitor(self) -> None:
        """Monitor keepalive timeouts for all sessions."""
        while True:
            try:
                for session in self.sessions.values():
                    session.check_keepalive_timeout()
                await asyncio.sleep(1.0)  # Check every second
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Keepalive monitor error: {e}")
                await asyncio.sleep(1.0)

    def get_all_sessions_info(self) -> dict[str, dict[str, Any]]:
        """Get information about all sessions."""
        return {peer_id: session.get_session_info() for peer_id, session in self.sessions.items()}
