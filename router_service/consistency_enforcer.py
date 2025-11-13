"""Consistency level enforcement for EVENTUAL vs RYW (Read-Your-Writes).

Implements session stickiness middleware that enforces read-your-writes consistency
by routing reads for active sessions to primary storage until replication lag
catches up. Supports configurable consistency levels per namespace/session.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from metrics.registry import REGISTRY

# Metrics for GAP-305
_RYW_READ_LATENCY = REGISTRY.histogram("ryw_read_latency_ms", [1, 5, 10, 25, 50, 100, 250, 500, 1000])
_RYW_SESSIONS_ACTIVE = REGISTRY.gauge("ryw_sessions_active")
_RYW_ENFORCEMENT_COUNT = REGISTRY.counter("ryw_enforcement_count")


ConsistencyLevel = Literal["EVENTUAL", "RYW"]


@dataclass
class SessionState:
    """Tracks session state for consistency enforcement."""

    session_id: str
    consistency_level: ConsistencyLevel
    created_at: float
    last_write_at: float | None = None
    namespace: str | None = None
    ttl_seconds: float = 300.0  # 5 minutes default

    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return (time.time() - self.created_at) > self.ttl_seconds

    @property
    def should_enforce_ryw(self) -> bool:
        """Check if RYW should be enforced for this session."""
        if self.consistency_level != "RYW":
            return False
        if self.last_write_at is None:
            return False
        # Enforce RYW for 2 seconds after last write (configurable replication lag)
        return (time.time() - self.last_write_at) < 2.0


class ConsistencyEnforcer:
    """Enforces consistency levels for sessions and namespaces."""

    def __init__(self, default_level: ConsistencyLevel = "EVENTUAL"):
        self.default_level = default_level
        self.sessions: dict[str, SessionState] = {}
        self.namespace_defaults: dict[str, ConsistencyLevel] = {}

    def set_namespace_default(self, namespace: str, level: ConsistencyLevel) -> None:
        """Set default consistency level for a namespace."""
        self.namespace_defaults[namespace] = level

    def start_session(
        self,
        session_id: str,
        consistency_level: ConsistencyLevel | None = None,
        namespace: str | None = None,
        ttl_seconds: float = 300.0,
    ) -> SessionState:
        """Start a new session with consistency enforcement."""
        level = consistency_level or self.namespace_defaults.get(namespace or "", self.default_level)
        session = SessionState(
            session_id=session_id,
            consistency_level=level,
            created_at=time.time(),
            namespace=namespace,
            ttl_seconds=ttl_seconds,
        )
        self.sessions[session_id] = session
        _RYW_SESSIONS_ACTIVE.set(len([s for s in self.sessions.values() if not s.is_expired]))
        return session

    def record_write(self, session_id: str, namespace: str) -> None:
        """Record a write operation for consistency tracking."""
        if session := self.sessions.get(session_id):
            session.last_write_at = time.time()
            session.namespace = namespace

    def should_route_to_primary(self, session_id: str | None, namespace: str) -> bool:
        """Determine if read should be routed to primary for consistency."""
        if not session_id:
            return False

        session = self.sessions.get(session_id)
        if not session or session.is_expired:
            return False

        # Clean up expired sessions
        self._cleanup_expired()

        should_enforce = session.should_enforce_ryw
        if should_enforce:
            _RYW_ENFORCEMENT_COUNT.inc()

        return should_enforce

    def get_session_consistency(self, session_id: str) -> ConsistencyLevel:
        """Get the consistency level for a session."""
        if session := self.sessions.get(session_id):
            if not session.is_expired:
                return session.consistency_level
        return self.default_level

    def _cleanup_expired(self) -> None:
        """Clean up expired sessions."""
        expired = [sid for sid, s in self.sessions.items() if s.is_expired]
        for sid in expired:
            del self.sessions[sid]
        if expired:
            _RYW_SESSIONS_ACTIVE.set(len(self.sessions))


# Global enforcer instance
_ENFORCER = ConsistencyEnforcer()


def get_enforcer() -> ConsistencyEnforcer:
    """Get the global consistency enforcer."""
    return _ENFORCER


def measure_ryw_latency(func):
    """Decorator to measure RYW read latency."""

    def wrapper(*args, **kwargs):
        start = time.time()
        try:
            return func(*args, **kwargs)
        finally:
            duration_ms = (time.time() - start) * 1000
            _RYW_READ_LATENCY.observe(duration_ms)

    return wrapper
