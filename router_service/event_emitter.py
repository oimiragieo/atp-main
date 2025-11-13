# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Rejection/Speculative Sampling Event Surfacing (GAP-135).

This module implements event types and metrics for rejection and speculative sampling scenarios,
providing structured observability for AI agent decision-making processes.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any

from metrics.registry import REGISTRY


class RejectionReason(Enum):
    """Enumeration of rejection reasons for structured event classification."""

    INPUT_VALIDATION = "input_validation"
    REPLAY_DETECTED = "replay_detected"
    POLICY_VIOLATION = "policy_violation"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    AUTHENTICATION_FAILED = "authentication_failed"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SCHEMA_MISMATCH = "schema_mismatch"
    MALFORMED_REQUEST = "malformed_request"


class SpeculativeEventType(Enum):
    """Enumeration of speculative sampling event types."""

    SPECULATION_ATTEMPTED = "speculation_attempted"
    SPECULATION_ACCEPTED = "speculation_accepted"
    SPECULATION_REJECTED = "speculation_rejected"
    EARLY_TERMINATION = "early_termination"
    LATENCY_SAVED = "latency_saved"


class RejectionEvent:
    """Structured event for rejection scenarios."""

    def __init__(
        self,
        reason: RejectionReason,
        component: str,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
        timestamp: float | None = None,
    ):
        """Initialize rejection event.

        Args:
            reason: Reason for rejection
            component: Component that rejected the request
            request_id: Optional request identifier
            details: Additional context details
            timestamp: Event timestamp (defaults to current time)
        """
        self.reason = reason
        self.component = component
        self.request_id = request_id
        self.details = details or {}
        self.timestamp = timestamp or time.time()

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary representation."""
        return {
            "event_type": "rejection",
            "reason": self.reason.value,
            "component": self.component,
            "request_id": self.request_id,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class SpeculativeEvent:
    """Structured event for speculative sampling scenarios."""

    def __init__(
        self,
        event_type: SpeculativeEventType,
        model_name: str,
        latency_saved_ms: float | None = None,
        confidence_score: float | None = None,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
        timestamp: float | None = None,
    ):
        """Initialize speculative event.

        Args:
            event_type: Type of speculative event
            model_name: Name of the model involved
            latency_saved_ms: Latency saved in milliseconds (for accepted speculations)
            confidence_score: Confidence score of the speculation
            request_id: Optional request identifier
            details: Additional context details
            timestamp: Event timestamp (defaults to current time)
        """
        self.event_type = event_type
        self.model_name = model_name
        self.latency_saved_ms = latency_saved_ms
        self.confidence_score = confidence_score
        self.request_id = request_id
        self.details = details or {}
        self.timestamp = timestamp or time.time()

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary representation."""
        return {
            "event_type": "speculative",
            "speculative_type": self.event_type.value,
            "model_name": self.model_name,
            "latency_saved_ms": self.latency_saved_ms,
            "confidence_score": self.confidence_score,
            "request_id": self.request_id,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class EventEmitter:
    """Central event emitter for rejection and speculative sampling events."""

    def __init__(self):
        """Initialize event emitter."""
        self._handlers: list[callable] = []

    def add_handler(self, handler: callable) -> None:
        """Add an event handler.

        Args:
            handler: Function that accepts event dictionaries
        """
        self._handlers.append(handler)

    def emit_rejection(self, event: RejectionEvent) -> None:  # noqa: S110
        """Emit a rejection event.

        Args:
            event: Rejection event to emit
        """
        event_dict = event.to_dict()
        for handler in self._handlers:
            try:
                handler(event_dict)
            except Exception as e:
                # Don't let handler failures break the main flow
                print(f"Warning: Event handler failed: {e}")  # TODO: Replace with proper logging

    def emit_speculative(self, event: SpeculativeEvent) -> None:  # noqa: S110
        """Emit a speculative sampling event.

        Args:
            event: Speculative event to emit
        """
        event_dict = event.to_dict()
        for handler in self._handlers:
            try:
                handler(event_dict)
            except Exception as e:
                # Don't let handler failures break the main flow
                print(f"Warning: Event handler failed: {e}")  # TODO: Replace with proper logging


# Global event emitter instance
_EVENT_EMITTER = EventEmitter()

# GAP-135: Speculative sampling event metrics
SPECULATIVE_EVENTS_TOTAL = REGISTRY.counter("speculative_events_total")


def get_event_emitter() -> EventEmitter:
    """Get the global event emitter instance."""
    return _EVENT_EMITTER


def emit_rejection_event(
    reason: RejectionReason,
    component: str,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Convenience function to emit a rejection event.

    Args:
        reason: Reason for rejection
        component: Component that rejected the request
        request_id: Optional request identifier
        details: Additional context details
    """
    event = RejectionEvent(reason, component, request_id, details)
    _EVENT_EMITTER.emit_rejection(event)


def emit_speculative_event(
    event_type: SpeculativeEventType,
    model_name: str,
    latency_saved_ms: float | None = None,
    confidence_score: float | None = None,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Convenience function to emit a speculative sampling event.

    Args:
        event_type: Type of speculative event
        model_name: Name of the model involved
        latency_saved_ms: Latency saved in milliseconds
        confidence_score: Confidence score of the speculation
        request_id: Optional request identifier
        details: Additional context details
    """
    event = SpeculativeEvent(event_type, model_name, latency_saved_ms, confidence_score, request_id, details)
    _EVENT_EMITTER.emit_speculative(event)
    # Increment the metric counter
    SPECULATIVE_EVENTS_TOTAL.inc(1)
