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

"""Tests for Rejection/Speculative Sampling Event Surfacing (GAP-135)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from router_service.event_emitter import (
    EventEmitter,
    RejectionEvent,
    RejectionReason,
    SpeculativeEvent,
    SpeculativeEventType,
    emit_rejection_event,
    emit_speculative_event,
)
from router_service.speculative_sampler import SpeculativeSampler


class TestRejectionEvent:
    """Test rejection event functionality."""

    def test_rejection_event_creation(self):
        """Test creating a rejection event."""
        event = RejectionEvent(RejectionReason.INPUT_VALIDATION, "test_component", "req-123", {"extra": "data"})

        assert event.reason == RejectionReason.INPUT_VALIDATION
        assert event.component == "test_component"
        assert event.request_id == "req-123"
        assert event.details == {"extra": "data"}
        assert isinstance(event.timestamp, float)

    def test_rejection_event_to_dict(self):
        """Test converting rejection event to dictionary."""
        event = RejectionEvent(RejectionReason.REPLAY_DETECTED, "replay_guard", "req-456")

        event_dict = event.to_dict()

        expected = {
            "event_type": "rejection",
            "reason": "replay_detected",
            "component": "replay_guard",
            "request_id": "req-456",
            "details": {},
        }

        # Check all expected fields (timestamp will vary)
        for key, value in expected.items():
            assert event_dict[key] == value
        assert "timestamp" in event_dict


class TestSpeculativeEvent:
    """Test speculative event functionality."""

    def test_speculative_event_creation(self):
        """Test creating a speculative event."""
        event = SpeculativeEvent(
            SpeculativeEventType.SPECULATION_ACCEPTED,
            "draft-model-v1",
            latency_saved_ms=15.5,
            confidence_score=0.85,
            request_id="req-789",
            details={"model_version": "1.0"},
        )

        assert event.event_type == SpeculativeEventType.SPECULATION_ACCEPTED
        assert event.model_name == "draft-model-v1"
        assert event.latency_saved_ms == 15.5
        assert event.confidence_score == 0.85
        assert event.request_id == "req-789"
        assert event.details == {"model_version": "1.0"}

    def test_speculative_event_to_dict(self):
        """Test converting speculative event to dictionary."""
        event = SpeculativeEvent(SpeculativeEventType.SPECULATION_REJECTED, "target-model-v1", confidence_score=0.45)

        event_dict = event.to_dict()

        expected = {
            "event_type": "speculative",
            "speculative_type": "speculation_rejected",
            "model_name": "target-model-v1",
            "latency_saved_ms": None,
            "confidence_score": 0.45,
            "request_id": None,
            "details": {},
        }

        for key, value in expected.items():
            assert event_dict[key] == value
        assert "timestamp" in event_dict


class TestEventEmitter:
    """Test event emitter functionality."""

    def test_event_emitter_add_handler(self):
        """Test adding event handlers."""
        emitter = EventEmitter()
        handler = MagicMock()

        emitter.add_handler(handler)
        assert len(emitter._handlers) == 1
        assert emitter._handlers[0] == handler

    def test_event_emitter_emit_rejection(self):
        """Test emitting rejection events."""
        emitter = EventEmitter()
        handler = MagicMock()

        emitter.add_handler(handler)

        event = RejectionEvent(RejectionReason.INPUT_VALIDATION, "test")
        emitter.emit_rejection(event)

        handler.assert_called_once()
        call_args = handler.call_args[0][0]
        assert call_args["event_type"] == "rejection"
        assert call_args["reason"] == "input_validation"

    def test_event_emitter_emit_speculative(self):
        """Test emitting speculative events."""
        emitter = EventEmitter()
        handler = MagicMock()

        emitter.add_handler(handler)

        event = SpeculativeEvent(SpeculativeEventType.SPECULATION_ACCEPTED, "model")
        emitter.emit_speculative(event)

        handler.assert_called_once()
        call_args = handler.call_args[0][0]
        assert call_args["event_type"] == "speculative"
        assert call_args["speculative_type"] == "speculation_accepted"

    def test_event_emitter_handler_failure(self):
        """Test that handler failures don't break event emission."""
        emitter = EventEmitter()

        # Add a handler that raises an exception
        failing_handler = MagicMock(side_effect=Exception("Handler failed"))
        working_handler = MagicMock()

        emitter.add_handler(failing_handler)
        emitter.add_handler(working_handler)

        event = RejectionEvent(RejectionReason.INPUT_VALIDATION, "test")
        emitter.emit_rejection(event)

        # The failing handler should have been called and failed
        failing_handler.assert_called_once()
        # The working handler should still have been called
        working_handler.assert_called_once()


class TestConvenienceFunctions:
    """Test convenience functions for event emission."""

    @patch("router_service.event_emitter._EVENT_EMITTER")
    def test_emit_rejection_event(self, mock_emitter):
        """Test emit_rejection_event convenience function."""
        emit_rejection_event(RejectionReason.POLICY_VIOLATION, "policy_engine", "req-123", {"policy": "test_policy"})

        mock_emitter.emit_rejection.assert_called_once()
        event = mock_emitter.emit_rejection.call_args[0][0]

        assert event.reason == RejectionReason.POLICY_VIOLATION
        assert event.component == "policy_engine"
        assert event.request_id == "req-123"
        assert event.details == {"policy": "test_policy"}

    @patch("router_service.event_emitter._EVENT_EMITTER")
    @patch("router_service.event_emitter.SPECULATIVE_EVENTS_TOTAL")
    def test_emit_speculative_event(self, mock_counter, mock_emitter):
        """Test emit_speculative_event convenience function."""
        emit_speculative_event(
            SpeculativeEventType.SPECULATION_ACCEPTED,
            "draft-model",
            latency_saved_ms=20.0,
            confidence_score=0.9,
            request_id="req-456",
        )

        mock_emitter.emit_speculative.assert_called_once()
        event = mock_emitter.emit_speculative.call_args[0][0]

        assert event.event_type == SpeculativeEventType.SPECULATION_ACCEPTED
        assert event.model_name == "draft-model"
        assert event.latency_saved_ms == 20.0
        assert event.confidence_score == 0.9
        assert event.request_id == "req-456"

        # Verify counter was incremented
        mock_counter.inc.assert_called_once_with(1)


class TestSpeculativeSampler:
    """Test speculative sampler functionality."""

    def test_speculative_sampler_creation(self):
        """Test creating a speculative sampler."""
        sampler = SpeculativeSampler(draft_model="draft-v1", target_model="target-v1", acceptance_threshold=0.8)

        assert sampler.draft_model == "draft-v1"
        assert sampler.target_model == "target-v1"
        assert sampler.acceptance_threshold == 0.8

    @patch("router_service.speculative_sampler.emit_speculative_event")
    def test_speculate_accepted(self, mock_emit):
        """Test speculative sampling with accepted speculation."""
        sampler = SpeculativeSampler(acceptance_threshold=0.5)

        # Mock to ensure high confidence (prefix match) and acceptance
        with (
            patch("random.choice", return_value="hello world"),
            patch("random.random", return_value=0.5),
            patch("time.sleep"),
        ):  # Skip actual sleep
            result = sampler.speculate("test prompt", "req-123")

            assert result["accepted"] is True
            assert result["confidence"] == 0.8  # High confidence for prefix match
            assert result["draft_response"] == "hello world"
            assert result["target_response"] == "hello world"  # Same response = high confidence
            assert result["effective_response"] == "hello world"
            assert result["latency_saved_ms"] > 0

            # Verify events were emitted
            assert mock_emit.call_count >= 2  # At least attempted and accepted

    @patch("router_service.speculative_sampler.emit_speculative_event")
    def test_speculate_rejected(self, mock_emit):
        """Test speculative sampling with rejected speculation."""
        sampler = SpeculativeSampler(acceptance_threshold=0.9)  # High threshold

        # Mock to ensure low confidence (mismatch)
        with (
            patch("random.choice", side_effect=["hello world", "goodbye world"]),
            patch("random.random", return_value=0.5),
            patch("time.sleep"),
        ):  # Skip actual sleep
            result = sampler.speculate("test prompt", "req-456")

            assert result["accepted"] is False
            assert result["confidence"] == 0.2  # Low confidence for mismatch
            assert result["latency_saved_ms"] == 0
            assert result["effective_response"] == "goodbye world"

            # Verify events were emitted
            assert mock_emit.call_count >= 2  # At least attempted and rejected

    def test_calculate_confidence(self):
        """Test confidence calculation."""
        sampler = SpeculativeSampler()

        # Test prefix match (high confidence)
        confidence = sampler._calculate_confidence("hello world", "hello universe")
        assert confidence == 0.8

        # Test mismatch (low confidence)
        confidence = sampler._calculate_confidence("hello world", "goodbye world")
        assert confidence == 0.2

        # Test empty strings
        confidence = sampler._calculate_confidence("", "hello")
        assert confidence == 0.0

    def test_benchmark(self):
        """Test benchmark functionality."""
        sampler = SpeculativeSampler()

        with patch.object(sampler, "speculate") as mock_speculate:
            # Mock speculate to return accepted results
            mock_speculate.return_value = {"accepted": True, "latency_saved_ms": 30.0, "confidence": 0.85}

            result = sampler.benchmark(trials=10)

            assert result["trials"] == 10
            assert result["acceptance_rate"] == 1.0  # All accepted
            assert result["average_latency_saved_ms"] == 30.0
            assert result["average_confidence"] == pytest.approx(0.85, rel=1e-2)
            assert result["total_speculative_events"] == 10

            # Verify speculate was called 10 times
            assert mock_speculate.call_count == 10


class TestIntegrationWithExistingComponents:
    """Test integration with existing rejection components."""

    @patch("router_service.input_hardening.emit_rejection_event")
    def test_input_hardening_integration(self, mock_emit):
        """Test that input hardening emits rejection events."""
        from router_service.input_hardening import check_input

        # Test invalid MIME - use data with many non-printable characters
        # This creates a byte string with many NUL bytes to trigger rejection
        invalid_data = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f" * 10
        result, reason = check_input(invalid_data, request_id="req-123")
        assert result is False
        assert reason == "invalid_mime"

        mock_emit.assert_called_once()
        call_args = mock_emit.call_args
        assert call_args[0][0] == RejectionReason.INPUT_VALIDATION
        assert call_args[0][1] == "input_hardening"
        assert call_args[0][2] == "req-123"

    @patch("router_service.replay_guard.emit_rejection_event")
    def test_replay_guard_integration(self, mock_emit):
        """Test that replay guard emits rejection events."""
        from router_service.replay_guard import NonceStore

        store = NonceStore()

        # First call should succeed
        result1 = store.check_and_store("nonce1", request_id="req-123")
        assert result1 is True

        # Second call with same nonce should fail and emit event
        result2 = store.check_and_store("nonce1", request_id="req-456")
        assert result2 is False

        mock_emit.assert_called_once()
        call_args = mock_emit.call_args
        assert call_args[0][0] == RejectionReason.REPLAY_DETECTED
        assert call_args[0][1] == "replay_guard"
        assert call_args[0][2] == "req-456"
