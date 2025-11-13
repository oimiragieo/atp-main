"""Sub-request Orchestrator (GAP-250)

Implements multi-turn reasoning orchestration with state machine for managing
sequences of sub-requests. Supports conversation flow control, dependency
management, and failure recovery for complex reasoning chains.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from metrics.registry import REGISTRY


class OrchestratorState(Enum):
    """States for the sub-request orchestrator."""

    IDLE = "idle"
    INITIALIZING = "initializing"
    EXECUTING = "executing"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OrchestratorEvent(Enum):
    """Events that can trigger state transitions."""

    START = "start"
    SUB_REQUEST_COMPLETE = "sub_request_complete"
    SUB_REQUEST_FAILED = "sub_request_failed"
    DEPENDENCY_READY = "dependency_ready"
    TIMEOUT = "timeout"
    CANCEL = "cancel"
    RESET = "reset"


@dataclass
class SubRequest:
    """Represents a single sub-request in the orchestration sequence."""

    request_id: str
    prompt: str
    adapter_name: str
    dependencies: list[str] = field(default_factory=list)
    timeout_seconds: float = 30.0
    retry_count: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    status: str = "pending"

    @property
    def is_completed(self) -> bool:
        """Check if the sub-request is completed."""
        return self.status in ["completed", "failed"]

    @property
    def is_successful(self) -> bool:
        """Check if the sub-request completed successfully."""
        return self.status == "completed"

    @property
    def duration(self) -> float | None:
        """Get the duration of the sub-request execution."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None


@dataclass
class OrchestrationSession:
    """Represents a complete orchestration session."""

    session_id: str
    initial_prompt: str
    state: OrchestratorState = OrchestratorState.IDLE
    sub_requests: dict[str, SubRequest] = field(default_factory=dict)
    execution_order: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    @property
    def is_active(self) -> bool:
        """Check if the session is currently active."""
        return self.state in [OrchestratorState.INITIALIZING, OrchestratorState.EXECUTING, OrchestratorState.WAITING]

    @property
    def is_completed(self) -> bool:
        """Check if the session is completed."""
        return self.state in [OrchestratorState.COMPLETED, OrchestratorState.FAILED, OrchestratorState.CANCELLED]

    @property
    def duration(self) -> float | None:
        """Get the total duration of the session."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None

    def get_pending_requests(self) -> list[SubRequest]:
        """Get all pending sub-requests."""
        return [req for req in self.sub_requests.values() if req.status == "pending"]

    def get_ready_requests(self) -> list[SubRequest]:
        """Get sub-requests that are ready to execute (all dependencies satisfied)."""
        ready = []
        for req in self.sub_requests.values():
            if req.status != "pending":
                continue
            # Check if all dependencies are completed successfully
            # Only consider dependencies that exist in this session
            deps_satisfied = all(
                self.sub_requests[dep_id].is_successful for dep_id in req.dependencies if dep_id in self.sub_requests
            )
            # If there are dependencies that don't exist in this session, they're not satisfied
            has_external_deps = any(dep_id not in self.sub_requests for dep_id in req.dependencies)
            if deps_satisfied and not has_external_deps:
                ready.append(req)
        return ready


class SubRequestOrchestrator:
    """Orchestrates multi-turn reasoning sequences with dependency management."""

    def __init__(self):
        self.sessions: dict[str, OrchestrationSession] = {}
        self.event_handlers: dict[OrchestratorEvent, list[Callable]] = {}

        # Metrics
        self._sessions_created = REGISTRY.counter("atp_orchestrator_sessions_created_total")
        self._sessions_completed = REGISTRY.counter("atp_orchestrator_sessions_completed_total")
        self._sessions_failed = REGISTRY.counter("atp_orchestrator_sessions_failed_total")
        self._sub_requests_created = REGISTRY.counter("atp_orchestrator_sub_requests_created_total")
        self._sub_requests_completed = REGISTRY.counter("atp_orchestrator_sub_requests_completed_total")
        self._sub_requests_failed = REGISTRY.counter("atp_orchestrator_sub_requests_failed_total")
        self._session_duration = REGISTRY.histogram(
            "atp_orchestrator_session_duration_seconds", [1, 5, 10, 30, 60, 300]
        )
        self._sub_request_duration = REGISTRY.histogram(
            "atp_orchestrator_sub_request_duration_seconds", [0.1, 0.5, 1, 5, 10, 30]
        )
        self._active_sessions = REGISTRY.gauge("atp_orchestrator_active_sessions")
        self._sub_requests_per_session = REGISTRY.histogram(
            "atp_orchestrator_sub_requests_per_session", [1, 2, 3, 5, 10, 20]
        )

    def create_session(self, initial_prompt: str) -> str:
        """Create a new orchestration session."""
        session_id = f"orch_{uuid.uuid4().hex[:8]}"
        session = OrchestrationSession(session_id=session_id, initial_prompt=initial_prompt)
        self.sessions[session_id] = session
        self._sessions_created.inc()
        self._active_sessions.inc()
        logging.info(f"Created orchestration session {session_id}")
        return session_id

    def add_sub_request(
        self,
        session_id: str,
        prompt: str,
        adapter_name: str,
        dependencies: list[str] | None = None,
        timeout_seconds: float = 30.0,
    ) -> str:
        """Add a sub-request to an orchestration session."""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        session = self.sessions[session_id]
        if session.is_completed:
            raise ValueError(f"Session {session_id} is already completed")

        request_id = f"req_{uuid.uuid4().hex[:8]}"
        sub_request = SubRequest(
            request_id=request_id,
            prompt=prompt,
            adapter_name=adapter_name,
            dependencies=dependencies or [],
            timeout_seconds=timeout_seconds,
        )

        session.sub_requests[request_id] = sub_request
        session.execution_order.append(request_id)
        self._sub_requests_created.inc()

        logging.info(f"Added sub-request {request_id} to session {session_id}")
        return request_id

    def start_session(self, session_id: str) -> None:
        """Start execution of an orchestration session."""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        session = self.sessions[session_id]
        if session.state != OrchestratorState.IDLE:
            raise ValueError(f"Session {session_id} is not in IDLE state")

        session.state = OrchestratorState.INITIALIZING
        session.started_at = time.time()

        # Find initial requests (no dependencies)
        ready_requests = session.get_ready_requests()
        if ready_requests:
            session.state = OrchestratorState.EXECUTING
            logging.info(f"Started orchestration session {session_id} with {len(ready_requests)} initial requests")
        else:
            logging.warning(f"No ready requests found for session {session_id}")

    def complete_sub_request(self, session_id: str, request_id: str, result: dict[str, Any]) -> None:
        """Mark a sub-request as completed with a result."""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        session = self.sessions[session_id]
        if request_id not in session.sub_requests:
            raise ValueError(f"Request {request_id} not found in session {session_id}")

        sub_request = session.sub_requests[request_id]
        if sub_request.status != "pending":
            logging.warning(f"Request {request_id} is already {sub_request.status}")
            return

        sub_request.status = "completed"
        sub_request.completed_at = time.time()
        sub_request.result = result
        self._sub_requests_completed.inc()

        if sub_request.duration:
            self._sub_request_duration.observe(sub_request.duration)

        logging.info(f"Completed sub-request {request_id} in session {session_id}")

        # Check if session is complete
        self._check_session_completion(session)

    def fail_sub_request(self, session_id: str, request_id: str, error: str) -> None:
        """Mark a sub-request as failed with an error."""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        session = self.sessions[session_id]
        if request_id not in session.sub_requests:
            raise ValueError(f"Request {request_id} not found in session {session_id}")

        sub_request = session.sub_requests[request_id]
        if sub_request.status != "pending":
            logging.warning(f"Request {request_id} is already {sub_request.status}")
            return

        sub_request.status = "failed"
        sub_request.completed_at = time.time()
        sub_request.error = error
        self._sub_requests_failed.inc()

        logging.error(f"Failed sub-request {request_id} in session {session_id}: {error}")

        # Check if session should fail
        self._check_session_completion(session)

    def _check_session_completion(self, session: OrchestrationSession) -> None:
        """Check if a session is complete and update its state."""
        pending_requests = session.get_pending_requests()
        failed_requests = [req for req in session.sub_requests.values() if req.status == "failed"]

        if not pending_requests:
            # All requests completed
            session.completed_at = time.time()
            if failed_requests:
                session.state = OrchestratorState.FAILED
                session.error = f"{len(failed_requests)} sub-request(s) failed"
                self._sessions_failed.inc()
            else:
                session.state = OrchestratorState.COMPLETED
                self._sessions_completed.inc()

            self._active_sessions.dec()
            if session.duration:
                self._session_duration.observe(session.duration)
                self._sub_requests_per_session.observe(len(session.sub_requests))

            logging.info(f"Session {session.session_id} completed with state {session.state.value}")

    def cancel_session(self, session_id: str) -> None:
        """Cancel an orchestration session."""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        session = self.sessions[session_id]
        if session.is_completed:
            return

        session.state = OrchestratorState.CANCELLED
        session.completed_at = time.time()
        self._active_sessions.dec()

        logging.info(f"Cancelled orchestration session {session_id}")

    def get_session_status(self, session_id: str) -> dict[str, Any] | None:
        """Get the current status of an orchestration session."""
        if session_id not in self.sessions:
            return None

        session = self.sessions[session_id]
        return {
            "session_id": session.session_id,
            "state": session.state.value,
            "created_at": session.created_at,
            "started_at": session.started_at,
            "completed_at": session.completed_at,
            "duration": session.duration,
            "sub_requests": {
                req_id: {
                    "status": req.status,
                    "adapter_name": req.adapter_name,
                    "dependencies": req.dependencies,
                    "created_at": req.created_at,
                    "started_at": req.started_at,
                    "completed_at": req.completed_at,
                    "duration": req.duration,
                    "error": req.error,
                }
                for req_id, req in session.sub_requests.items()
            },
        }


# Global orchestrator instance
_ORCHESTRATOR = SubRequestOrchestrator()


def get_orchestrator() -> SubRequestOrchestrator:
    """Get the global sub-request orchestrator instance."""
    return _ORCHESTRATOR
