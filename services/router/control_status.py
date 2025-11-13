"""POC: Agent CTRL/STATUS states (GAP-084).

Tracks per-session agent status and computes effective window adjustments.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any

from metrics.registry import REGISTRY

_CTR_STATUS_CHANGES = REGISTRY.counter("agent_status_changes_total")
_CTR_WINDOW_OVERRIDES = REGISTRY.counter("window_overrides_applied")
_CTR_PAUSES_HONORED = REGISTRY.counter("pauses_honored_total")


class Status(str, Enum):
    READY = "READY"
    BUSY = "BUSY"
    PAUSE = "PAUSE"
    DRAINING = "DRAINING"


class AgentStatus:
    def __init__(self, grace_ms: int = 5000) -> None:
        self._by_session: dict[str, Status] = {}
        self._pause_grace_until: dict[str, float] = {}  # session -> timestamp when grace expires
        self._grace_ms = grace_ms

    def set_status(self, session: str, status: Status) -> None:
        prev = self._by_session.get(session)
        if prev != status:
            self._by_session[session] = status
            _CTR_STATUS_CHANGES.inc(1)

            # Handle PAUSE grace period
            if status == Status.PAUSE:
                self._pause_grace_until[session] = time.time() + (self._grace_ms / 1000.0)
            elif prev == Status.PAUSE and status != Status.PAUSE:
                # Clear grace period when leaving PAUSE
                self._pause_grace_until.pop(session, None)

    def get_status(self, session: str) -> Status:
        return self._by_session.get(session, Status.READY)

    def _is_in_pause_grace_period(self, session: str) -> bool:
        """Check if session is currently in PAUSE grace period."""
        if self.get_status(session) != Status.PAUSE:
            return False
        grace_until = self._pause_grace_until.get(session)
        if grace_until is None:
            return False
        return time.time() < grace_until

    def effective_window(self, session: str, router_allowed: int, suggested: int | None = None) -> int:
        """Return effective window size applying status and suggested min logic.

        - READY: min(router_allowed, suggested or router_allowed)
        - BUSY: 0 (stop new work)
        - PAUSE: 0 after grace_ms, router_allowed during grace period
        - DRAINING: allow at most 1 in-flight
        """
        st = self.get_status(session)
        if st == Status.BUSY:
            return 0
        if st == Status.PAUSE:
            if self._is_in_pause_grace_period(session):
                _CTR_PAUSES_HONORED.inc(1)
                # During grace period, allow normal window
                eff = router_allowed
                if suggested is not None:
                    original_eff = eff
                    eff = min(eff, max(0, int(suggested)))
                    if eff < original_eff:
                        _CTR_WINDOW_OVERRIDES.inc()
                return eff
            else:
                # Grace period expired, enforce PAUSE
                return 0
        if st == Status.DRAINING:
            return min(1, router_allowed)
        # READY
        eff = router_allowed
        if suggested is not None:
            original_eff = eff
            eff = min(eff, max(0, int(suggested)))
            if eff < original_eff:
                _CTR_WINDOW_OVERRIDES.inc()
        return eff

    def compute_capacity_reduction_factor(self) -> float:
        """Compute capacity reduction factor based on agent status distribution.

        Returns a factor between 0.0 and 1.0 where:
        - 1.0 = no reduction (all agents READY)
        - 0.0 = maximum reduction (all agents BUSY/PAUSE)
        - Values in between based on proportion of affected agents
        """
        if not self._by_session:
            return 1.0  # No sessions = no reduction

        total_sessions = len(self._by_session)
        busy_pause_sessions = sum(1 for status in self._by_session.values() if status in (Status.BUSY, Status.PAUSE))

        # Calculate reduction factor
        # BUSY/PAUSE agents cause capacity reduction
        reduction_factor = 1.0 - (busy_pause_sessions / total_sessions)

        return max(0.0, min(1.0, reduction_factor))  # Clamp to [0.0, 1.0]

    def get_backpressure_status(self) -> dict[str, Any]:
        """Get backpressure status summary for AGP integration."""
        factor = self.compute_capacity_reduction_factor()
        busy_pause_count = sum(1 for status in self._by_session.values() if status in (Status.BUSY, Status.PAUSE))

        return {
            "capacity_reduction_factor": factor,
            "busy_pause_agents": busy_pause_count,
            "total_agents": len(self._by_session),
            "backpressure_active": factor < 1.0,
        }

    def broadcast_status(self, session: str) -> dict:
        """Return a simple status event payload (POC for broadcast)."""
        return {"type": "agent.status", "session": session, "status": self.get_status(session)}


GLOBAL_AGENT_STATUS = AgentStatus()
