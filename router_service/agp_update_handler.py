#!/usr/bin/env python3
"""
AGP UPDATE Message Handling and Attribute Validation

Implements AGP UPDATE message parsing, attribute validation, and route management
according to the AGP Federation Specification.
"""

from __future__ import annotations

import json
import os
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Add memory-gateway to path for audit_log import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "memory-gateway")))
import audit_log as audit_log_module  # renamed for lint N812 compliance
from metrics.registry import REGISTRY, Histogram

from router_service.adaptive_reconciliation import (
    SwitchingContext,
    get_adaptive_reconciliation_strategy,
)
from router_service.arpki_validator import validate_agp_route_attestation
from router_service.control_status import GLOBAL_AGENT_STATUS
from router_service.tracing import get_tracer

# Arbiter metrics
_CTR_ARBITER_INVOCATIONS = REGISTRY.counter("arbiter_invocations_total")
_CTR_ARBITER_BUDGET_EXCEEDED = REGISTRY.counter("arbiter_budget_exceeded_total")


class ParallelSessionState(Enum):
    """Parallel session states for persona adapter orchestration."""

    INIT = "init"  # Router allocates persona set
    DISPATCHED = "dispatched"  # RPCs sent to adapters
    STREAMING = "streaming"  # Adapters emit token streams
    BUFFERING = "buffering"  # Router aggregates outputs
    RECONCILING = "reconciling"  # Reconciliation policy applied
    COMPLETE = "complete"  # Merged result returned to client


@dataclass
class ParallelSessionConfig:
    """Configuration for parallel session management."""

    max_buffer_tokens: int = 256  # Default buffer size per persona
    reconciliation_timeout_s: float = 30.0  # Max time for reconciliation
    enable_metrics: bool = True
    buffer_timeout_s: float = 5.0  # Max time to wait for missing sequences
    qos_buffer_multipliers: dict[str, float] = field(
        default_factory=lambda: {
            "gold": 0.5,  # Smaller buffer for low-latency
            "silver": 1.0,  # Default buffer size
            "bronze": 2.0,  # Larger buffer for compliance
        }
    )


class ReconciliationStrategy(ABC):
    """Abstract base class for reconciliation strategies."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def reconcile(self, session: ParallelSession) -> dict[str, Any]:
        """Reconcile results from multiple personas."""
        pass

    @abstractmethod
    def can_reconcile(self, session: ParallelSession) -> bool:
        """Check if reconciliation can proceed."""
        pass


class IncrementalReconciliationStrategy(ABC):
    """Abstract base class for incremental reconciliation strategies."""

    @abstractmethod
    def can_incremental_reconcile(self, session: ParallelSession) -> bool:
        """Check if incremental reconciliation can proceed."""
        pass

    @abstractmethod
    def incremental_reconcile(
        self, session: ParallelSession, completed_personas: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Perform incremental reconciliation on completed personas."""
        pass

    @abstractmethod
    def should_flush_partial(self, session: ParallelSession) -> bool:
        """Check if partial results should be flushed due to backpressure."""
        pass


class FirstWinStrategy(ReconciliationStrategy, IncrementalReconciliationStrategy):
    """First persona to complete wins strategy."""

    def __init__(self):
        super().__init__("first-win")

    def can_reconcile(self, session: ParallelSession) -> bool:
        """Can reconcile if at least one persona completed."""
        return any(p.get("completed", False) for p in session.personas)

    def can_incremental_reconcile(self, session: ParallelSession) -> bool:
        """Can incremental reconcile if at least one persona completed."""
        return self.can_reconcile(session)

    def incremental_reconcile(
        self, session: ParallelSession, completed_personas: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Incremental reconciliation - same as full reconcile for first-win."""
        if not completed_personas:
            raise ValueError("No personas completed")

        # Return the first completed persona's buffered data
        first_persona = min(completed_personas, key=lambda p: p.get("completed_at", float("inf")))
        result = self._reconcile_persona(session, first_persona)
        result["incremental"] = True
        return result

    def should_flush_partial(self, session: ParallelSession) -> bool:
        """Flush partial results if buffer is getting full."""
        total_buffered = sum(
            len(item.get("data", "")) for buffer_items in session.buffers.values() for item in buffer_items
        )
        return total_buffered > session.config.max_buffer_tokens * 0.8  # 80% threshold

    def reconcile(self, session: ParallelSession) -> dict[str, Any]:
        """First persona to complete wins."""
        completed_personas = [p for p in session.personas if p.get("completed")]
        if not completed_personas:
            raise ValueError("No personas completed")

        # Return the first completed persona's buffered data
        first_persona = min(completed_personas, key=lambda p: p.get("completed_at", float("inf")))
        result = self._reconcile_persona(session, first_persona)
        result["policy"] = self.name
        return result

    def _reconcile_persona(self, session: ParallelSession, persona: dict[str, Any]) -> dict[str, Any]:
        """Helper to reconcile a single persona."""
        persona_id = persona["persona_id"]
        clone_id = persona.get("clone_id")

        # Create buffer key that includes clone_id if specified
        buffer_key = f"{persona_id}-{clone_id}" if clone_id is not None else persona_id

        # Concatenate all buffered data for this persona/clone
        data_parts = []
        for item in sorted(session.buffers.get(buffer_key, []), key=lambda x: x["seq"]):
            data_parts.append(item["data"])

        return {
            "result": "".join(data_parts),
            "winning_persona": persona_id,
            "winning_clone_id": clone_id,
            "policy": self.name,
        }


class ConsensusStrategy(ReconciliationStrategy, IncrementalReconciliationStrategy):
    """Majority consensus strategy."""

    def __init__(self, majority_threshold: float = 0.5):
        super().__init__("consensus")
        self.majority_threshold = majority_threshold

    def can_reconcile(self, session: ParallelSession) -> bool:
        """Can reconcile if majority of personas completed."""
        completed_count = sum(1 for p in session.personas if p.get("completed"))
        total_count = len(session.personas)
        return completed_count / total_count >= self.majority_threshold

    def can_incremental_reconcile(self, session: ParallelSession) -> bool:
        """Can incremental reconcile if majority reached."""
        return self.can_reconcile(session)

    def incremental_reconcile(
        self, session: ParallelSession, completed_personas: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Incremental consensus reconciliation."""
        if not completed_personas:
            raise ValueError("No personas completed")

        # For incremental, use first-win among completed personas
        first_win = FirstWinStrategy()
        result = first_win.incremental_reconcile(session, completed_personas)
        result["policy"] = self.name
        result["incremental"] = True
        return result

    def should_flush_partial(self, session: ParallelSession) -> bool:
        """Flush when majority is reached and buffer is filling up."""
        if not self.can_reconcile(session):
            return False
        total_buffered = sum(
            len(item.get("data", "")) for buffer_items in session.buffers.values() for item in buffer_items
        )
        return total_buffered > session.config.max_buffer_tokens * 0.6  # 60% threshold for consensus

    def reconcile(self, session: ParallelSession) -> dict[str, Any]:
        """Apply consensus reconciliation."""
        completed_personas = [p for p in session.personas if p.get("completed")]
        if not completed_personas:
            raise ValueError("No personas completed")

        # For now, delegate to first-win if consensus reached
        first_win = FirstWinStrategy()
        result = first_win.reconcile(session)
        result["policy"] = self.name
        return result


class WeightedMergeStrategy(ReconciliationStrategy, IncrementalReconciliationStrategy):
    """Weighted merge strategy combining all persona outputs."""

    def __init__(self, weights: dict[str, float] | None = None):
        super().__init__("weighted-merge")
        self.weights = weights or {}

    def can_reconcile(self, session: ParallelSession) -> bool:
        """Can reconcile if at least one persona completed."""
        return any(p.get("completed", False) for p in session.personas)

    def can_incremental_reconcile(self, session: ParallelSession) -> bool:
        """Can incremental reconcile if at least one persona completed."""
        return self.can_reconcile(session)

    def should_flush_partial(self, session: ParallelSession) -> bool:
        """Flush when buffer is getting full."""
        total_buffered = sum(
            len(item.get("data", "")) for buffer_items in session.buffers.values() for item in buffer_items
        )
        return total_buffered > session.config.max_buffer_tokens * 0.7  # 70% threshold for weighted merge

    def incremental_reconcile(
        self, session: ParallelSession, completed_personas: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Incremental weighted merge reconciliation."""
        if not completed_personas:
            raise ValueError("No personas completed")

        # For incremental, use simple concatenation with weights
        result_parts = []
        total_weight = 0.0
        for persona in completed_personas:
            persona_id = persona["persona_id"]
            weight = self.weights.get(persona_id, 1.0)
            total_weight += weight
            result_parts.append(f"[{persona_id}:{weight}]")

        result = {
            "result": " ".join(result_parts),
            "policy": self.name,
            "incremental": True,
            "total_weight": total_weight,
            "completed_count": len(completed_personas),
            "total_personas": len(session.personas),
        }
        return result

    def reconcile(self, session: ParallelSession) -> dict[str, Any]:
        """Apply weighted merge reconciliation."""
        completed_personas = [p for p in session.personas if p.get("completed")]
        if not completed_personas:
            raise ValueError("No personas completed")

        # Collect all results with weights
        result_parts = []
        total_weight = 0.0
        for persona in completed_personas:
            persona_id = persona["persona_id"]
            clone_id = persona.get("clone_id")
            buffer_key = f"{persona_id}-{clone_id}" if clone_id is not None else persona_id

            data_parts = []
            for item in sorted(session.buffers.get(buffer_key, []), key=lambda x: x["seq"]):
                data_parts.append(item["data"])
            persona_result = "".join(data_parts)

            weight = self.weights.get(persona_id, 1.0)
            total_weight += weight
            result_parts.append(f"{persona_result} [{persona_id}:{weight}]")

        result = {"result": " ".join(result_parts), "policy": self.name, "total_weight": total_weight}
        return result


class ArbiterReconciliationStrategy(ReconciliationStrategy, IncrementalReconciliationStrategy):
    """LLM-based arbiter reconciliation strategy for divergent findings."""

    def __init__(self, max_usd_budget: float = 0.10, fallback_strategy: ReconciliationStrategy | None = None):
        super().__init__("arbiter")
        self.max_usd_budget = max_usd_budget
        self.fallback_strategy = fallback_strategy or FirstWinStrategy()
        self._budget_used = 0.0

    def can_reconcile(self, session: ParallelSession) -> bool:
        """Can reconcile if all personas completed and budget allows."""
        if not all(p.get("completed", False) for p in session.personas):
            return False
        return self._budget_used < self.max_usd_budget

    def can_incremental_reconcile(self, session: ParallelSession) -> bool:
        """Can incremental reconcile if budget allows."""
        return self._budget_used < self.max_usd_budget

    def should_flush_partial(self, session: ParallelSession) -> bool:
        """Flush when budget is running low."""
        return self._budget_used > self.max_usd_budget * 0.8

    def incremental_reconcile(
        self, session: ParallelSession, completed_personas: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Incremental arbiter reconciliation."""
        if not completed_personas:
            raise ValueError("No personas completed")

        # For incremental, use fallback strategy
        result = self.fallback_strategy.reconcile(session)
        result["policy"] = self.name
        result["arbiter_used"] = False
        result["incremental"] = True
        return result

    def reconcile(self, session: ParallelSession) -> dict[str, Any]:
        """LLM-based arbiter reconciliation for divergent findings."""
        completed_personas = [p for p in session.personas if p.get("completed")]
        if not completed_personas:
            raise ValueError("No personas completed")

        # Collect all results
        all_results = []
        for persona in completed_personas:
            persona_id = persona["persona_id"]
            clone_id = persona.get("clone_id")
            buffer_key = f"{persona_id}-{clone_id}" if clone_id is not None else persona_id

            data_parts = []
            for item in sorted(session.buffers.get(buffer_key, []), key=lambda x: x["seq"]):
                data_parts.append(item["data"])
            persona_result = "".join(data_parts)
            all_results.append(
                {
                    "persona_id": persona_id,
                    "clone_id": clone_id,
                    "result": persona_result,
                    "stats": persona.get("stats", {}),
                }
            )

        # Check if arbiter is needed (divergent results)
        if self._results_are_divergent(all_results):
            if self._budget_used >= self.max_usd_budget:
                # Budget exceeded, use fallback
                _CTR_ARBITER_BUDGET_EXCEEDED.inc()
                result = self.fallback_strategy.reconcile(session)
                result["policy"] = self.name
                result["arbiter_used"] = False
                result["budget_exceeded"] = True
                return result

            # Use LLM arbiter
            _CTR_ARBITER_INVOCATIONS.inc()
            arbiter_result = self._invoke_arbiter(all_results)
            self._budget_used += arbiter_result.get("cost_usd", 0.05)  # Estimate cost

            return {
                "result": arbiter_result["reconciled_result"],
                "policy": self.name,
                "arbiter_used": True,
                "arbiter_reasoning": arbiter_result.get("reasoning", ""),
                "budget_used": self._budget_used,
                "original_results": all_results,
            }
        else:
            # Results are similar enough, use first result
            result = self.fallback_strategy.reconcile(session)
            result["policy"] = self.name
            result["arbiter_used"] = False
            result["results_converged"] = True
            return result

    def _results_are_divergent(self, results: list[dict[str, Any]]) -> bool:
        """Check if results are divergent enough to warrant arbiter."""
        if len(results) <= 1:
            return False

        # Simple divergence check: compare result lengths and content similarity
        first_result = results[0]["result"]
        for result in results[1:]:
            if abs(len(first_result) - len(result["result"])) > 100:  # Significant length difference
                return True
            # Could add more sophisticated similarity checks here

        return False

    def _invoke_arbiter(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        """Invoke LLM arbiter to reconcile divergent results."""
        # This is a placeholder for actual LLM integration
        # In a real implementation, this would call an LLM API

        # For now, return a mock result
        return {
            "reconciled_result": results[0]["result"],  # Use first result as arbiter decision
            "reasoning": "Mock arbiter decision - using first result",
            "cost_usd": 0.05,
            "confidence": 0.8,
        }


@dataclass
class ParallelSession:
    """Manages a parallel session state machine for persona orchestration."""

    session_id: str
    config: ParallelSessionConfig
    state: ParallelSessionState = ParallelSessionState.INIT
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    personas: list[dict[str, Any]] = field(default_factory=list)
    buffers: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    reconciliation_policy: str = "first-win"
    arbiter_max_usd: float = 0.10
    adaptive_reconciliation_enabled: bool = False
    result: dict[str, Any] | None = None
    error: str | None = None
    buffer_wait_ms_histogram: Histogram | None = None

    def __post_init__(self) -> None:
        """Initialize session buffers for each persona."""
        for persona in self.personas:
            persona_id = persona.get("persona_id", "unknown")
            self.buffers[persona_id] = []

    def transition_to(self, new_state: ParallelSessionState) -> None:
        """Transition to a new state with validation."""
        # Validate state transitions
        valid_transitions = {
            ParallelSessionState.INIT: [ParallelSessionState.DISPATCHED],
            ParallelSessionState.DISPATCHED: [ParallelSessionState.STREAMING],
            ParallelSessionState.STREAMING: [ParallelSessionState.BUFFERING, ParallelSessionState.RECONCILING],
            ParallelSessionState.BUFFERING: [ParallelSessionState.RECONCILING],
            ParallelSessionState.RECONCILING: [ParallelSessionState.COMPLETE],
            ParallelSessionState.COMPLETE: [],  # Terminal state
        }

        if new_state not in valid_transitions.get(self.state, []):
            raise ValueError(f"Invalid transition from {self.state.value} to {new_state.value}")

        self.state = new_state
        self.updated_at = time.time()

    def add_persona(self, persona: dict[str, Any]) -> None:
        """Add a persona to the session."""
        if self.state != ParallelSessionState.INIT:
            raise ValueError("Can only add personas in INIT state")

        self.personas.append(persona)
        persona_id = persona.get("persona_id", "unknown")
        self.buffers[persona_id] = []

    def buffer_stream_data(
        self, persona_id: str, seq: int, data: str, qos: str = "silver", clone_id: int | None = None
    ) -> None:
        """Buffer streaming data from a persona with out-of-order handling."""
        if self.state not in [ParallelSessionState.STREAMING, ParallelSessionState.BUFFERING]:
            raise ValueError("Can only buffer data in STREAMING or BUFFERING state")

        # Start stream span
        tracer = get_tracer()
        span_cm = tracer.start_as_current_span("stream.buffer") if tracer else None
        if span_cm:
            span_cm.__enter__()
            if hasattr(tracer, "_get_current_span"):
                span = tracer._get_current_span()
                if span:
                    span.set_attribute("session.id", self.session_id)
                    span.set_attribute("persona.id", persona_id)
                    span.set_attribute("stream.seq", seq)
                    span.set_attribute("stream.qos", qos)
                    span.set_attribute("stream.clone_id", clone_id)
                    span.set_attribute("stream.data_len", len(data))

        try:
            # Create buffer key that includes clone_id if specified
            if clone_id is not None:
                buffer_key = f"{persona_id}-{clone_id}"
            else:
                # Backward compatibility: try to find a persona with matching persona_id
                matching_personas = [p for p in self.personas if p.get("persona_id") == persona_id]
                if len(matching_personas) == 1 and matching_personas[0].get("clone_id"):
                    # If there's exactly one persona with this ID and it has a clone_id, use it
                    buffer_key = f"{persona_id}-{matching_personas[0]['clone_id']}"
                else:
                    # Fallback to original behavior
                    buffer_key = persona_id

            if buffer_key not in self.buffers:
                self.buffers[buffer_key] = []

            # Calculate buffer limit based on QoS tier
            base_limit = self.config.max_buffer_tokens
            multiplier = self.config.qos_buffer_multipliers.get(qos, 1.0)
            buffer_limit = int(base_limit * multiplier)

            # Check buffer size limit
            current_size = sum(len(item.get("data", "")) for item in self.buffers[buffer_key])
            if current_size + len(data) > buffer_limit:
                raise ValueError(f"Buffer overflow for persona {buffer_key} (limit: {buffer_limit})")

            # Store data with sequence number and timestamp
            buffer_entry = {"seq": seq, "data": data, "timestamp": time.time(), "received_at": time.time()}

            # Insert in sequence order (not just append)
            self._insert_ordered_buffer(buffer_key, buffer_entry)

            # Try to fill any gaps that can now be filled
            self._fill_sequence_gaps(buffer_key)
        finally:
            if span_cm:
                span_cm.__exit__(None, None, None)

    def _insert_ordered_buffer(self, persona_id: str, entry: dict[str, Any]) -> None:
        """Insert buffer entry in sequence order."""
        buffer = self.buffers[persona_id]
        seq = entry["seq"]

        # Find insertion point
        insert_idx = 0
        for i, item in enumerate(buffer):
            if item["seq"] > seq:
                break
            insert_idx = i + 1

        buffer.insert(insert_idx, entry)

    def _fill_sequence_gaps(self, persona_id: str) -> None:
        """Attempt to fill sequence gaps that are now complete."""
        buffer = self.buffers[persona_id]
        if not buffer:
            return

        # Check for gaps and timeouts
        expected_seq = 1
        current_time = time.time()

        for i, entry in enumerate(buffer):
            seq = entry["seq"]
            age = current_time - entry["received_at"]

            if seq == expected_seq:
                expected_seq += 1
            elif seq > expected_seq:
                # Gap detected
                if age > self.config.buffer_timeout_s:
                    # Timeout: fill gap with empty data
                    gap_entry = {
                        "seq": expected_seq,
                        "data": "",  # Gap filler
                        "timestamp": entry["timestamp"],
                        "received_at": current_time,
                        "gap_filled": True,
                    }
                    buffer.insert(i, gap_entry)
                    expected_seq += 1
                    # Recursively try to fill more gaps
                    self._fill_sequence_gaps(persona_id)
                    break
            # If seq < expected_seq, it's a duplicate or out-of-order, skip

        # Track wait times for filled gaps
        if self.buffer_wait_ms_histogram:
            for entry in buffer:
                if entry.get("gap_filled") and "wait_time_recorded" not in entry:
                    # Calculate wait time from when the gap was detected until now
                    wait_time_ms = (current_time - entry["received_at"]) * 1000
                    self.buffer_wait_ms_histogram.observe(wait_time_ms)
                    entry["wait_time_recorded"] = True

    def get_ordered_buffer_data(self, persona_id: str) -> list[dict[str, Any]]:
        """Get buffer data in sequence order, filling gaps as needed."""
        if persona_id not in self.buffers:
            return []

        buffer = self.buffers[persona_id]
        self._fill_sequence_gaps(persona_id)  # Final gap fill attempt

        return buffer.copy()

    def get_buffer_stats(self, persona_id: str) -> dict[str, Any]:
        """Get buffer statistics for a persona."""
        if persona_id not in self.buffers:
            return {"total_entries": 0, "total_tokens": 0, "gaps": 0, "oldest_age": 0}

        buffer = self.buffers[persona_id]
        current_time = time.time()

        total_tokens = sum(len(item.get("data", "")) for item in buffer)
        gaps = sum(1 for item in buffer if item.get("gap_filled", False))
        oldest_age = max((current_time - item["received_at"] for item in buffer), default=0)

        return {"total_entries": len(buffer), "total_tokens": total_tokens, "gaps": gaps, "oldest_age": oldest_age}

    def mark_persona_complete(self, persona_id: str, stats: dict[str, Any], clone_id: int | None = None) -> None:
        """Mark a persona as completed with statistics."""
        # Find the persona and add completion stats
        for persona in self.personas:
            current_persona_id = persona.get("persona_id")
            current_clone_id = persona.get("clone_id")

            # Match by persona_id if no clone_id specified, or by both if clone_id specified
            if clone_id is None:
                # Backward compatibility: match by persona_id only
                if current_persona_id == persona_id:
                    persona["completed"] = True
                    persona["stats"] = stats
                    persona["completed_at"] = time.time()
                    break
            else:
                # New behavior: match by persona_id and clone_id
                if current_persona_id == persona_id and current_clone_id == clone_id:
                    persona["completed"] = True
                    persona["stats"] = stats
                    persona["completed_at"] = time.time()
                    break

        # Check if all personas are complete
        all_complete = all(p.get("completed", False) for p in self.personas)
        if all_complete and self.state == ParallelSessionState.STREAMING:
            self.transition_to(ParallelSessionState.BUFFERING)

    def reconcile_results(self) -> dict[str, Any]:
        """Apply reconciliation policy and return final result."""
        if self.state != ParallelSessionState.RECONCILING:
            raise ValueError("Can only reconcile in RECONCILING state")

        strategy = self._get_reconciliation_strategy()
        if not strategy.can_reconcile(self):
            raise ValueError(f"Cannot reconcile with strategy {strategy.name}")

        return strategy.reconcile(self)

    def _get_reconciliation_strategy(self) -> ReconciliationStrategy:
        """Get the appropriate reconciliation strategy."""
        # Determine the actual policy to use
        actual_policy = self.reconciliation_policy

        if self.adaptive_reconciliation_enabled:
            # Create switching context from session data
            context = SwitchingContext(
                request_complexity=self._estimate_request_complexity(),
                time_pressure=self._detect_time_pressure(),
                cost_sensitivity=self._estimate_cost_sensitivity(),
                quality_requirement=self._estimate_quality_requirement(),
                persona_count=len(self.personas),
                convergence_history=self._get_recent_convergence_history(),
            )

            # Get adaptive recommendation
            actual_policy = get_adaptive_reconciliation_strategy(context)

        # Instantiate the strategy
        if actual_policy == "first-win":
            return FirstWinStrategy()
        elif actual_policy == "consensus":
            return ConsensusStrategy()
        elif actual_policy == "weighted-merge":
            return WeightedMergeStrategy()
        elif actual_policy == "arbiter":
            return ArbiterReconciliationStrategy(max_usd_budget=self.arbiter_max_usd)
        else:
            raise ValueError(f"Unknown reconciliation policy: {actual_policy}")

    def _estimate_request_complexity(self) -> float:
        """Estimate request complexity based on persona count and types."""
        # Simple heuristic: more personas = more complex
        base_complexity = min(len(self.personas) / 5.0, 1.0)

        # Adjust based on persona types (if available)
        specialized_count = sum(1 for p in self.personas if p.get("type", "") in ["reasoning", "analysis"])
        if specialized_count > 0:
            base_complexity = min(base_complexity + 0.2, 1.0)

        return base_complexity

    def _detect_time_pressure(self) -> bool:
        """Detect if there's time pressure for this request."""
        # Check for timeout hints in session config
        timeout = getattr(self.config, "reconciliation_timeout_s", 30.0)
        return timeout < 10.0  # Less than 10 seconds = high time pressure

    def _estimate_cost_sensitivity(self) -> float:
        """Estimate cost sensitivity based on arbiter budget."""
        # Lower budget = higher cost sensitivity
        budget = self.arbiter_max_usd
        if budget < 0.05:
            return 0.9  # Very cost sensitive
        elif budget < 0.10:
            return 0.6  # Moderately cost sensitive
        else:
            return 0.3  # Not very cost sensitive

    def _estimate_quality_requirement(self) -> float:
        """Estimate quality requirements based on persona composition."""
        # More specialized personas = higher quality requirements
        specialized_personas = sum(1 for p in self.personas if p.get("type", "") in ["reasoning", "analysis", "expert"])
        return min(specialized_personas / len(self.personas), 1.0)

    def _get_recent_convergence_history(self) -> list[bool]:
        """Get recent convergence outcomes (placeholder for now)."""
        # In a real implementation, this would track recent reconciliation successes
        return [True] * 5  # Assume recent successes

    # Legacy methods for backward compatibility
    def _reconcile_first_win(self) -> dict[str, Any]:
        """First persona to complete wins."""
        strategy = FirstWinStrategy()
        return strategy.reconcile(self)

    def _reconcile_consensus(self) -> dict[str, Any]:
        """Majority agreement required."""
        strategy = ConsensusStrategy()
        return strategy.reconcile(self)

    def _reconcile_weighted_merge(self) -> dict[str, Any]:
        """Merge all outputs with weights."""
        strategy = WeightedMergeStrategy()
        return strategy.reconcile(self)

    def can_streaming_reconcile(self) -> bool:
        """Check if streaming reconciliation is possible."""
        strategy = self._get_reconciliation_strategy()
        if isinstance(strategy, IncrementalReconciliationStrategy):
            return strategy.can_incremental_reconcile(self)
        return False

    def streaming_reconcile(self) -> dict[str, Any] | None:
        """Perform streaming reconciliation if possible."""
        if not self.can_streaming_reconcile():
            return None

        completed_personas = [p for p in self.personas if p.get("completed")]
        if not completed_personas:
            return None

        strategy = self._get_reconciliation_strategy()
        if isinstance(strategy, IncrementalReconciliationStrategy):
            return strategy.incremental_reconcile(self, completed_personas)
        return None

    def should_flush_streaming(self) -> bool:
        """Check if streaming results should be flushed due to backpressure."""
        strategy = self._get_reconciliation_strategy()
        if isinstance(strategy, IncrementalReconciliationStrategy):
            return strategy.should_flush_partial(self)
        return False


class ParallelSessionManager:
    """Manages multiple parallel sessions."""

    def __init__(self, config: ParallelSessionConfig | None = None):
        self.config = config or ParallelSessionConfig()
        self.sessions: dict[str, ParallelSession] = {}
        self.parallel_sessions_active = REGISTRY.gauge("parallel_sessions_active")
        self.dispatch_targets_total = REGISTRY.gauge("dispatch_targets_total")
        self.buffer_wait_ms = REGISTRY.histogram("buffer_wait_ms", [10, 50, 100, 500, 1000, 5000])
        self.reconciliation_strategy_counts = REGISTRY.counter("reconciliation_strategy_counts")
        self.streaming_reconcile_sessions_total = REGISTRY.counter("streaming_reconcile_sessions_total")
        self.clone_id_counter = 0  # Global clone ID allocator

        # Audit log setup
        self._data_dir = os.getenv("ROUTER_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
        self._audit_file = os.path.join(self._data_dir, "reconciliation_audit.jsonl")
        self._audit_secret = os.getenv("AUDIT_SECRET", "default-audit-secret").encode("utf-8")
        self._last_audit_hash: str | None = None

    def _audit_event(self, event: dict[str, Any]) -> None:
        """Log an audit event for reconciliation operations."""
        os.makedirs(self._data_dir, exist_ok=True)
        self._last_audit_hash = audit_log_module.append_event(
            self._audit_file, event, self._audit_secret, self._last_audit_hash
        )

    def allocate_clones(self, persona_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Allocate clone IDs for persona specifications.

        Args:
            persona_specs: List of {"persona_id": str, "count": int} or {"persona_id": str}

        Returns:
            List of personas with allocated clone_ids
        """
        personas = []
        for spec in persona_specs:
            persona_id = spec["persona_id"]
            count = spec.get("count", 1)

            for _ in range(count):
                self.clone_id_counter += 1
                personas.append({"persona_id": persona_id, "clone_id": self.clone_id_counter})

        return personas

    def create_session_with_clones(
        self,
        session_id: str,
        persona_specs: list[dict[str, Any]],
        reconciliation_policy: str = "first-win",
        arbiter_max_usd: float = 0.10,
    ) -> ParallelSession:
        """Create a new parallel session with automatic clone allocation.

        Args:
            session_id: Unique session identifier
            persona_specs: List of {"persona_id": str, "count": int} specifications
            reconciliation_policy: Reconciliation strategy to use
            arbiter_max_usd: Maximum USD budget for LLM arbiter

        Returns:
            ParallelSession with allocated clones
        """
        personas = self.allocate_clones(persona_specs)
        return self.create_session(session_id, personas, reconciliation_policy, arbiter_max_usd)

    def create_session(
        self,
        session_id: str,
        personas: list[dict[str, Any]],
        reconciliation_policy: str = "first-win",
        arbiter_max_usd: float = 0.10,
    ) -> ParallelSession:
        """Create a new parallel session."""
        # Start dispatch span
        tracer = get_tracer()
        span_cm = tracer.start_as_current_span("dispatch.session") if tracer else None
        if span_cm:
            span_cm.__enter__()
            if hasattr(tracer, "_get_current_span"):
                span = tracer._get_current_span()
                if span:
                    span.set_attribute("session.id", session_id)
                    span.set_attribute("dispatch.personas", len(personas))
                    span.set_attribute("reconciliation.policy", reconciliation_policy)

        try:
            session = ParallelSession(
                session_id=session_id,
                config=self.config,
                personas=personas,
                reconciliation_policy=reconciliation_policy,
                arbiter_max_usd=arbiter_max_usd,
                buffer_wait_ms_histogram=self.buffer_wait_ms,
            )
            self.sessions[session_id] = session
            self._update_metrics()

            # Audit session creation
            audit_event = {
                "timestamp": time.time(),
                "event_type": "session_created",
                "session_id": session_id,
                "persona_count": len(personas),
                "reconciliation_policy": reconciliation_policy,
            }
            self._audit_event(audit_event)

            return session
        finally:
            if span_cm:
                span_cm.__exit__(None, None, None)

    def get_session(self, session_id: str) -> ParallelSession | None:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    def mark_persona_complete_and_check_streaming(
        self, session_id: str, persona_id: str, stats: dict[str, Any], clone_id: int | None = None
    ) -> dict[str, Any] | None:
        """Mark persona complete and check for streaming reconciliation."""
        session = self.get_session(session_id)
        if not session:
            return None

        # Mark persona complete
        session.mark_persona_complete(persona_id, stats, clone_id)

        # Check for streaming reconciliation
        if session.can_streaming_reconcile():
            return self.streaming_reconcile_session(session_id)
        return None

    def remove_session(self, session_id: str) -> None:
        """Remove a completed session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            self._update_metrics()

    def reconcile_session(self, session_id: str) -> dict[str, Any]:
        """Reconcile results for a session and record metrics."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Record reconciliation strategy usage
        self.reconciliation_strategy_counts.inc()

        # Start reconciliation span
        tracer = get_tracer()
        span_cm = tracer.start_as_current_span("reconciliation.session") if tracer else None
        if span_cm:
            span_cm.__enter__()
            if hasattr(tracer, "_get_current_span"):
                span = tracer._get_current_span()
                if span:
                    span.set_attribute("session.id", session_id)
                    span.set_attribute("session.personas", len(session.personas))
                    span.set_attribute("reconciliation.policy", session.reconciliation_policy)

        try:
            # Perform reconciliation
            result = session.reconcile_results()

            # Audit the reconciliation
            audit_event = {
                "timestamp": time.time(),
                "event_type": "reconciliation_complete",
                "session_id": session_id,
                "policy": session.reconciliation_policy,
                "persona_count": len(session.personas),
                "result_summary": {"has_result": "result" in result, "policy_used": result.get("policy", "unknown")},
            }
            self._audit_event(audit_event)

            return result
        finally:
            if span_cm:
                span_cm.__exit__(None, None, None)

    def streaming_reconcile_session(self, session_id: str) -> dict[str, Any] | None:
        """Attempt streaming reconciliation for a session."""
        session = self.get_session(session_id)
        if not session:
            return None

        # Check if streaming reconciliation is possible
        if not session.can_streaming_reconcile():
            return None

        # Record streaming reconciliation
        self.streaming_reconcile_sessions_total.inc()

        # Start streaming reconciliation span
        tracer = get_tracer()
        span_cm = tracer.start_as_current_span("streaming.reconciliation") if tracer else None
        if span_cm:
            span_cm.__enter__()
            if hasattr(tracer, "_get_current_span"):
                span = tracer._get_current_span()
                if span:
                    span.set_attribute("session.id", session_id)
                    span.set_attribute("streaming", True)

        try:
            # Perform streaming reconciliation
            result = session.streaming_reconcile()
            if result:
                # Audit the streaming reconciliation
                audit_event = {
                    "timestamp": time.time(),
                    "event_type": "streaming_reconciliation",
                    "session_id": session_id,
                    "policy": session.reconciliation_policy,
                    "completed_personas": result.get("completed_count", 0),
                    "total_personas": len(session.personas),
                    "incremental": result.get("incremental", False),
                }
                self._audit_event(audit_event)
            return result
        finally:
            if span_cm:
                span_cm.__exit__(None, None, None)

    def _update_metrics(self) -> None:
        """Update active sessions and dispatch targets metrics."""
        self.parallel_sessions_active.set(len(self.sessions))

        # Count total dispatch targets across all sessions
        total_targets = sum(len(session.personas) for session in self.sessions.values())
        self.dispatch_targets_total.set(total_targets)

    def cleanup_expired_sessions(self, max_age_s: float = 3600.0) -> int:
        """Clean up sessions older than max_age_s. Returns count removed."""
        now = time.time()
        expired = []

        for session_id, session in self.sessions.items():
            if now - session.created_at > max_age_s:
                expired.append(session_id)

        for session_id in expired:
            del self.sessions[session_id]

        if expired:
            self._update_metrics()

        return len(expired)


# Import statement for time was already present


@dataclass
class HysteresisConfig:
    """Configuration for health metric hysteresis and EWMA smoothing."""

    # Hysteresis parameters (from AGP Federation Spec)
    change_threshold_percent: float = 10.0  # X% change required to trigger update
    stabilization_period_seconds: int = 5  # Y seconds to wait before advertising change
    metric_type: str = "fast"  # "fast" or "slow" metrics

    # EWMA smoothing parameters
    ewma_alpha: float = 0.1  # Smoothing factor (higher = more responsive, lower = smoother)
    ewma_enabled: bool = True  # Whether to apply EWMA smoothing

    def validate(self) -> None:
        """Validate hysteresis configuration."""
        if self.change_threshold_percent <= 0:
            raise ValueError("change_threshold_percent must be positive")
        if self.stabilization_period_seconds <= 0:
            raise ValueError("stabilization_period_seconds must be positive")
        if self.metric_type not in ["fast", "slow"]:
            raise ValueError("metric_type must be 'fast' or 'slow'")
        if not (0 < self.ewma_alpha <= 1):
            raise ValueError("ewma_alpha must be between 0 and 1")


@dataclass
class EWMASmoother:
    """Exponential Weighted Moving Average smoother for health metrics."""

    alpha: float = 0.1  # Smoothing factor
    smoothed_value: float | None = None
    last_update_time: float | None = None

    def update(self, new_value: float, current_time: float | None = None) -> float:
        """Update the smoothed value with a new measurement."""
        if current_time is None:
            current_time = time.time()

        if self.smoothed_value is None:
            # First measurement
            self.smoothed_value = new_value
        else:
            # Apply EWMA: smoothed = alpha * new + (1 - alpha) * previous
            self.smoothed_value = self.alpha * new_value + (1 - self.alpha) * self.smoothed_value

        self.last_update_time = current_time
        return self.smoothed_value

    def get_smoothed_value(self) -> float | None:
        """Get the current smoothed value."""
        return self.smoothed_value

    def reset(self) -> None:
        """Reset the smoother."""
        self.smoothed_value = None
        self.last_update_time = None


@dataclass
class HoldDownConfig:
    """Configuration for hold-down and grace periods."""

    # Hold-down and grace period parameters (from AGP Federation Spec)
    persist_seconds: int = 8  # Hold-down: require degradation to persist for this many seconds
    grace_seconds: int = 5  # Grace period: suppress re-announcement for this many seconds after recovery

    def validate(self) -> None:
        """Validate hold-down configuration."""
        if self.persist_seconds <= 0:
            raise ValueError("persist_seconds must be positive")
        if self.grace_seconds <= 0:
            raise ValueError("grace_seconds must be positive")


@dataclass
class HealthMetricsProcessor:
    """Processes health metrics with EWMA smoothing and hysteresis."""

    hysteresis_config: HysteresisConfig
    ewma_smoother: EWMASmoother | None = None
    last_advertised_value: float | None = None
    last_change_time: float | None = None
    current_smoothed_value: float | None = None
    suppressed_updates: int = 0

    def __post_init__(self) -> None:
        """Initialize the EWMA smoother if enabled."""
        if self.hysteresis_config.ewma_enabled:
            self.ewma_smoother = EWMASmoother(alpha=self.hysteresis_config.ewma_alpha)

    def should_advertise_update(self, new_p95: float, current_time: float | None = None) -> bool:
        """Determine if a health update should be advertised based on hysteresis rules."""
        if current_time is None:
            current_time = time.time()

        # Apply EWMA smoothing if enabled
        if self.ewma_smoother:
            smoothed_p95 = self.ewma_smoother.update(new_p95, current_time)
        else:
            smoothed_p95 = new_p95

        # Track current smoothed value
        self.current_smoothed_value = smoothed_p95

        # First advertisement
        if self.last_advertised_value is None:
            self.last_advertised_value = smoothed_p95
            self.last_change_time = current_time
            return True

        # Calculate percentage change from last advertised value
        percent_change = abs(smoothed_p95 - self.last_advertised_value) / self.last_advertised_value * 100

        # Check if change exceeds threshold
        if percent_change >= self.hysteresis_config.change_threshold_percent:
            # Check if enough time has passed since last change
            if (
                self.last_change_time is None
                or (current_time - self.last_change_time) >= self.hysteresis_config.stabilization_period_seconds
            ):
                # Update should be advertised
                self.last_advertised_value = smoothed_p95
                self.last_change_time = current_time
                return True
            else:
                # Change detected but not enough time has passed
                self.suppressed_updates += 1
                return False
        else:
            # Change is below threshold
            self.suppressed_updates += 1
            return False

    def get_smoothed_value(self) -> float | None:
        """Get the current smoothed p95 value."""
        if self.ewma_smoother:
            return self.ewma_smoother.get_smoothed_value()
        return self.current_smoothed_value

    def reset(self) -> None:
        """Reset the processor state."""
        self.last_advertised_value = None
        self.last_change_time = None
        self.current_smoothed_value = None
        self.suppressed_updates = 0
        if self.ewma_smoother:
            self.ewma_smoother.reset()


@dataclass
class RouteDampeningConfig:
    """Configuration for route flap dampening."""

    # Dampening parameters (from AGP Federation Spec)
    penalty_per_flap: int = 1000  # Penalty points per flap
    suppress_threshold: int = 2000  # Suppress when penalty exceeds this
    reuse_threshold: int = 750  # Allow reuse when penalty drops below this
    max_penalty: int = 16000  # Maximum penalty cap
    half_life_minutes: int = 15  # Decay half-life in minutes
    max_flaps_per_minute: int = 6  # Flap detection threshold

    def validate(self) -> None:
        """Validate dampening configuration."""
        if self.penalty_per_flap <= 0:
            raise ValueError("penalty_per_flap must be positive")
        if self.suppress_threshold <= 0:
            raise ValueError("suppress_threshold must be positive")
        if self.reuse_threshold <= 0:
            raise ValueError("reuse_threshold must be positive")
        if self.max_penalty <= 0:
            raise ValueError("max_penalty must be positive")
        if self.half_life_minutes <= 0:
            raise ValueError("half_life_minutes must be positive")
        if self.max_flaps_per_minute <= 0:
            raise ValueError("max_flaps_per_minute must be positive")


@dataclass
class SafeModeConfig:
    """Configuration for safe mode fallback."""

    # Safe mode parameters (from AGP Federation Spec)
    enabled: bool = True  # Whether safe mode is enabled
    snapshot_path: str = "/var/lib/atp/snapshots/last_known_good.json"  # Path to last-known-good snapshot
    max_retries: int = 3  # Maximum number of policy load retries before entering safe mode
    retry_delay_seconds: int = 5  # Delay between retries

    def validate(self) -> None:
        """Validate safe mode configuration."""
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.retry_delay_seconds <= 0:
            raise ValueError("retry_delay_seconds must be positive")
        if not self.snapshot_path:
            raise ValueError("snapshot_path must not be empty")


@dataclass
class DampeningState:
    """State tracking for route dampening."""

    penalty: int = 0
    last_flap_time: float = 0.0
    flap_count: int = 0
    last_minute_start: float = 0.0
    suppressed: bool = False

    def record_flap(self, current_time: float, config: RouteDampeningConfig) -> None:
        """Record a route flap and update penalty."""
        self.last_flap_time = current_time
        self.flap_count += 1

        # Check if we're in a new minute for flap rate calculation
        if current_time - self.last_minute_start >= 60:
            self.last_minute_start = current_time
            self.flap_count = 1

        # Apply penalty
        self.penalty = min(self.penalty + config.penalty_per_flap, config.max_penalty)

        # Check if we should suppress
        if self.penalty >= config.suppress_threshold:
            self.suppressed = True

    def decay_penalty(self, current_time: float, config: RouteDampeningConfig) -> None:
        """Decay penalty over time using exponential decay."""
        if self.penalty == 0:
            return

        time_elapsed = current_time - self.last_flap_time
        if time_elapsed <= 0:
            return

        # Exponential decay: penalty *= (0.5)^(time_elapsed / half_life)
        half_life_seconds = config.half_life_minutes * 60
        decay_factor = (0.5) ** (time_elapsed / half_life_seconds)
        self.penalty = int(self.penalty * decay_factor)

        # Clear suppression if penalty drops below reuse threshold
        if self.suppressed and self.penalty < config.reuse_threshold:
            self.suppressed = False

    def is_suppressed(self, current_time: float, config: RouteDampeningConfig) -> bool:
        """Check if route is currently suppressed."""
        self.decay_penalty(current_time, config)
        return self.suppressed

    def should_suppress_due_to_flaps(self, current_time: float, config: RouteDampeningConfig) -> bool:
        """Check if route should be suppressed due to excessive flapping."""
        # Decay penalty first
        self.decay_penalty(current_time, config)

        # Check flap rate
        if current_time - self.last_minute_start < 60:
            if self.flap_count >= config.max_flaps_per_minute:
                return True

        return False


@dataclass
class HoldDownState:
    """State tracking for hold-down and grace periods."""

    # Hold-down timer: prevents withdrawal until degradation persists
    hold_down_until: float = 0.0  # Time when hold-down period expires
    last_health_degraded_time: float = 0.0  # When health first degraded

    # Grace period timer: prevents re-advertisement after recovery
    grace_period_until: float = 0.0  # Time when grace period expires
    last_recovery_time: float = 0.0  # When route last recovered

    def start_hold_down(self, current_time: float, config: HoldDownConfig) -> None:
        """Start hold-down timer when health degrades."""
        self.last_health_degraded_time = current_time
        self.hold_down_until = current_time + config.persist_seconds

    def start_grace_period(self, current_time: float, config: HoldDownConfig) -> None:
        """Start grace period when route recovers."""
        self.last_recovery_time = current_time
        self.grace_period_until = current_time + config.grace_seconds

    def is_in_hold_down(self, current_time: float) -> bool:
        """Check if route is currently in hold-down period."""
        return current_time < self.hold_down_until

    def is_in_grace_period(self, current_time: float) -> bool:
        """Check if route is currently in grace period."""
        return current_time < self.grace_period_until

    def clear_timers(self) -> None:
        """Clear all timers."""
        self.hold_down_until = 0.0
        self.grace_period_until = 0.0
        self.last_health_degraded_time = 0.0
        self.last_recovery_time = 0.0


class RouteDampeningTracker:
    """Tracks route flap dampening state per prefix."""

    def __init__(
        self,
        config: RouteDampeningConfig | None = None,
        hysteresis_config: HysteresisConfig | None = None,
        hold_down_config: HoldDownConfig | None = None,
        time_func: callable = None,
    ):
        self.config = config or RouteDampeningConfig()
        self.config.validate()
        self.hysteresis_config = hysteresis_config or HysteresisConfig()
        self.hysteresis_config.validate()
        self.hold_down_config = hold_down_config or HoldDownConfig()
        self.hold_down_config.validate()
        self.dampening_states: dict[str, DampeningState] = {}  # prefix -> state
        self.hold_down_states: dict[str, HoldDownState] = {}  # prefix -> hold-down state
        self._time_func = time_func or time.time

    def record_route_change(self, prefix: str, is_withdrawal: bool) -> None:
        """Record a route advertisement or withdrawal."""
        current_time = self._time_func()

        if prefix not in self.dampening_states:
            self.dampening_states[prefix] = DampeningState()

        state = self.dampening_states[prefix]

        # Decay existing penalty
        state.decay_penalty(current_time, self.config)

        # Record flap for withdrawals (route going down) or re-advertisements
        if is_withdrawal or state.last_flap_time > 0:
            state.record_flap(current_time, self.config)

    def is_suppressed(self, prefix: str) -> bool:
        """Check if a prefix is currently suppressed due to dampening."""
        current_time = self._time_func()

        if prefix not in self.dampening_states:
            return False

        state = self.dampening_states[prefix]
        return state.is_suppressed(current_time, self.config)

    def should_suppress_due_to_flaps(self, prefix: str) -> bool:
        """Check if a prefix should be suppressed due to excessive flapping."""
        current_time = time.time()

        if prefix not in self.dampening_states:
            return False

        state = self.dampening_states[prefix]
        return state.should_suppress_due_to_flaps(current_time, self.config)

    def get_dampening_info(self, prefix: str) -> dict[str, Any]:
        """Get dampening information for a prefix."""
        current_time = self._time_func()

        if prefix not in self.dampening_states:
            return {"penalty": 0, "suppressed": False, "flap_count": 0, "last_flap_seconds_ago": None}

        state = self.dampening_states[prefix]
        state.decay_penalty(current_time, self.config)

        return {
            "penalty": state.penalty,
            "suppressed": state.suppressed,
            "flap_count": state.flap_count,
            "last_flap_seconds_ago": current_time - state.last_flap_time if state.last_flap_time > 0 else None,
        }

    def record_health_change(self, prefix: str, health_degraded: bool, current_time: float | None = None) -> None:
        """Record a health-based route change for hold-down/grace period tracking."""
        current_time = current_time or self._time_func()

        if prefix not in self.hold_down_states:
            self.hold_down_states[prefix] = HoldDownState()

        state = self.hold_down_states[prefix]

        if health_degraded:
            # Health degraded - start hold-down timer only if not already in hold-down
            if not state.is_in_hold_down(current_time):
                # Clear any existing grace period when degradation starts
                state.grace_period_until = 0.0
                state.start_hold_down(current_time, self.hold_down_config)
        else:
            # Health recovered - start grace period only if not already in grace period
            if not state.is_in_grace_period(current_time):
                # Clear any existing hold-down when recovery starts
                state.hold_down_until = 0.0
                state.start_grace_period(current_time, self.hold_down_config)

    def should_delay_withdrawal(self, prefix: str, current_time: float | None = None) -> bool:
        """Check if withdrawal should be delayed due to hold-down period."""
        current_time = current_time or self._time_func()

        if prefix not in self.hold_down_states:
            return False

        state = self.hold_down_states[prefix]
        return state.is_in_hold_down(current_time)

    def should_delay_advertisement(self, prefix: str, current_time: float | None = None) -> bool:
        """Check if advertisement should be delayed due to grace period."""
        current_time = current_time or self._time_func()

        if prefix not in self.hold_down_states:
            return False

        state = self.hold_down_states[prefix]
        return state.is_in_grace_period(current_time)

    def get_hold_down_info(self, prefix: str) -> dict[str, Any]:
        """Get hold-down and grace period information for a prefix."""
        current_time = self._time_func()

        if prefix not in self.hold_down_states:
            return {
                "in_hold_down": False,
                "in_grace_period": False,
                "hold_down_remaining_seconds": 0,
                "grace_period_remaining_seconds": 0,
            }

        state = self.hold_down_states[prefix]

        return {
            "in_hold_down": state.is_in_hold_down(current_time),
            "in_grace_period": state.is_in_grace_period(current_time),
            "hold_down_remaining_seconds": max(0, state.hold_down_until - current_time),
            "grace_period_remaining_seconds": max(0, state.grace_period_until - current_time),
        }

    def cleanup_expired_states(self, max_age_seconds: int = 3600) -> None:
        """Clean up old dampening states."""
        current_time = self._time_func()
        to_remove = []

        for prefix, state in self.dampening_states.items():
            if current_time - state.last_flap_time > max_age_seconds and state.penalty == 0:
                to_remove.append(prefix)

        for prefix in to_remove:
            del self.dampening_states[prefix]

    def clear_all_states(self) -> None:
        """Clear all dampening states."""
        self.dampening_states.clear()

    def restore_state(self, prefix: str, state_info: dict[str, Any]) -> None:
        """Restore dampening state for a prefix."""
        state = DampeningState()
        state.penalty = state_info.get("penalty", 0)
        state.suppressed = state_info.get("suppressed", False)
        state.flap_count = state_info.get("flap_count", 0)
        state.last_flap_time = time.time() - (state_info.get("last_flap_seconds_ago") or 0)
        self.dampening_states[prefix] = state


@dataclass
class RouteSelectionConfig:
    """Configuration for AGP route selection algorithm weights."""

    # Path selection weights (from AGP Federation Spec Appendix A)
    local_pref_weight: float = 0.25
    path_len_weight: float = 0.15
    health_weight: float = 0.15
    cost_weight: float = 0.15
    predict_weight: float = 0.10
    qos_fit_weight: float = 0.05
    overhead_weight: float = 0.15

    # ECMP configuration
    enable_ecmp: bool = True
    max_ecmp_paths: int = 8
    ecmp_hash_seed: str = "agp-ecmp-v1"

    def validate(self) -> None:
        """Validate configuration weights."""
        weights = [
            self.local_pref_weight,
            self.path_len_weight,
            self.health_weight,
            self.cost_weight,
            self.predict_weight,
            self.qos_fit_weight,
            self.overhead_weight,
        ]

        if not all(0 <= w <= 1 for w in weights):
            raise ValueError("All weights must be between 0 and 1")

        total = sum(weights)
        if not (0.99 <= total <= 1.01):  # Allow small floating point tolerance
            raise ValueError(f"Weights must sum to 1.0, got {total}")

        if self.max_ecmp_paths < 1:
            raise ValueError("max_ecmp_paths must be at least 1")


class AGPMessageType(Enum):
    """AGP message types."""

    OPEN = "OPEN"
    KEEPALIVE = "KEEPALIVE"
    UPDATE = "UPDATE"
    ROUTE_REFRESH = "ROUTE_REFRESH"
    ERROR = "ERROR"


class ValidationError(Exception):
    """Raised when AGP message validation fails."""

    pass


@dataclass
class AGPRouteAttributes:
    """AGP route attributes as defined in the federation spec."""

    # Path attributes
    path: list[int]  # ADN path vector for loop prevention
    next_hop: str  # Router ID of next hop

    # Loop prevention attributes (GAP-109A)
    originator_id: str | None = None  # First advertiser inside the cluster
    cluster_list: list[str] | None = None  # Loop prevention across RRs

    # Preference attributes
    local_pref: int | None = None
    med: int | None = None

    # QoS and capacity
    qos_supported: list[str] | None = None
    capacity: dict[str, Any] | None = None

    # Health metrics
    health: dict[str, Any] | None = None

    # Cost and predictability
    cost: dict[str, Any] | None = None
    predictability: dict[str, Any] | None = None

    # Overhead calibration telemetry (GAP-109C)
    overhead: dict[str, Any] | None = None

    # Policy attributes
    communities: list[str] | None = None
    security_groups: list[str] | None = None
    regions: list[str] | None = None

    # Validity
    valid_until: float | None = None

    def validate(self) -> None:
        """Validate route attributes."""
        if not self.path:
            raise ValidationError("Path cannot be empty")

        if not self.next_hop:
            raise ValidationError("Next hop cannot be empty")

        # Validate path contains valid ADNs (32-bit unsigned)
        for adn in self.path:
            if not isinstance(adn, int) or adn < 0 or adn > 0xFFFFFFFF:
                raise ValidationError(f"Invalid ADN in path: {adn}")

        # Validate local_pref range
        if self.local_pref is not None and (self.local_pref < 0 or self.local_pref > 0xFFFFFFFF):
            raise ValidationError(f"Invalid local_pref: {self.local_pref}")

        # Validate MED range
        if self.med is not None and (self.med < 0 or self.med > 0xFFFFFFFF):
            raise ValidationError(f"Invalid MED: {self.med}")

        # Validate QoS tiers
        if self.qos_supported:
            valid_tiers = {"gold", "silver", "bronze", "platinum"}
            for tier in self.qos_supported:
                if tier not in valid_tiers:
                    raise ValidationError(f"Invalid QoS tier: {tier}")

        # Validate capacity structure
        if self.capacity:
            required_keys = {"max_parallel", "tokens_per_s", "usd_per_s"}
            if not all(key in self.capacity for key in required_keys):
                raise ValidationError("Capacity missing required fields")

        # Validate health structure
        if self.health:
            required_keys = {"p50_ms", "p95_ms", "err_rate"}
            if not all(key in self.health for key in required_keys):
                raise ValidationError("Health missing required fields")

        # Validate cost structure
        if self.cost is not None:
            if "usd_per_1k_tokens" not in self.cost:
                raise ValidationError("Cost missing usd_per_1k_tokens")

        # Validate predictability structure
        if self.predictability:
            required_keys = {"estimate_mape_7d", "under_rate_7d"}
            if not all(key in self.predictability for key in required_keys):
                raise ValidationError("Predictability missing required fields")

        # Policy validation: QoS Fit
        if self.qos_supported:
            # Define QoS hierarchy (higher index = higher quality)
            qos_hierarchy = {"bronze": 0, "silver": 1, "gold": 2, "platinum": 3}
            route_qqos_levels = [qos_hierarchy.get(qos, -1) for qos in self.qos_supported]
            max_qqos_level = max(route_qqos_levels) if route_qqos_levels else -1

            # Require at least bronze QoS support
            if max_qqos_level < 0:  # No valid QoS levels
                raise ValidationError("Route must support at least bronze QoS")

            # Require at least silver QoS for production routes
            if max_qqos_level < 1:  # Less than silver
                raise ValidationError("Route must support at least silver QoS for production")

        # Policy validation: no-export community enforcement
        if self.communities:
            for community in self.communities:
                if community == "no-export":
                    # Routes with no-export should not be accepted for re-advertisement
                    raise ValidationError("no-export routes not accepted")

        # Note: Expiration check is done separately via is_expired() method
        # to allow processing of recently expired routes

    def is_expired(self) -> bool:
        """Check if route has expired."""
        return self.valid_until is not None and self.valid_until < time.time()

    def to_dict(self) -> dict[str, Any]:
        """Serialize attributes to dictionary."""
        return {
            "path": self.path,
            "next_hop": self.next_hop,
            "originator_id": self.originator_id,
            "cluster_list": self.cluster_list,
            "local_pref": self.local_pref,
            "med": self.med,
            "qos_supported": self.qos_supported,
            "capacity": self.capacity,
            "health": self.health,
            "cost": self.cost,
            "predictability": self.predictability,
            "communities": self.communities,
            "security_groups": self.security_groups,
            "regions": self.regions,
            "valid_until": self.valid_until,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AGPRouteAttributes:
        """Deserialize attributes from dictionary."""
        return cls(
            path=data["path"],
            next_hop=data["next_hop"],
            originator_id=data.get("originator_id"),
            cluster_list=data.get("cluster_list"),
            local_pref=data.get("local_pref"),
            med=data.get("med"),
            qos_supported=data.get("qos_supported"),
            capacity=data.get("capacity"),
            health=data.get("health"),
            cost=data.get("cost"),
            predictability=data.get("predictability"),
            communities=data.get("communities"),
            security_groups=data.get("security_groups"),
            regions=data.get("regions"),
            valid_until=data.get("valid_until"),
        )


@dataclass
class AGPRoute:
    """AGP route object."""

    prefix: str
    attributes: AGPRouteAttributes
    received_at: float
    peer_router_id: str

    def __post_init__(self):
        """Validate route after initialization."""
        self.attributes.validate()

    def is_valid(self) -> bool:
        """Check if route is still valid."""
        return not self.attributes.is_expired()

    def to_dict(self) -> dict[str, Any]:
        """Serialize route to dictionary."""
        return {
            "prefix": self.prefix,
            "attributes": self.attributes.to_dict(),
            "received_at": self.received_at,
            "peer_router_id": self.peer_router_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AGPRoute:
        """Deserialize route from dictionary."""
        return cls(
            prefix=data["prefix"],
            attributes=AGPRouteAttributes.from_dict(data["attributes"]),
            received_at=data["received_at"],
            peer_router_id=data["peer_router_id"],
        )


@dataclass
class AGPUpdateMessage:
    """AGP UPDATE message structure."""

    type: str = AGPMessageType.UPDATE.value
    announce: list[dict[str, Any]] | None = None
    withdraw: list[str] | None = None

    def validate(self) -> None:
        """Validate UPDATE message structure."""
        if self.type != AGPMessageType.UPDATE.value:
            raise ValidationError(f"Invalid message type: {self.type}")

        # Must have either announce or withdraw
        if not self.announce and not self.withdraw:
            raise ValidationError("UPDATE message must have announce or withdraw")

        # Validate announce section
        if self.announce:
            for route_data in self.announce:
                if "prefix" not in route_data or "attrs" not in route_data:
                    raise ValidationError("Announce missing prefix or attrs")
                if "path" not in route_data["attrs"] or "next_hop" not in route_data["attrs"]:
                    raise ValidationError("Route attrs missing path or next_hop")

    def parse_routes(self, peer_router_id: str) -> tuple[list[AGPRoute], list[str]]:
        """Parse routes from UPDATE message."""
        announced_routes = []
        withdrawn_prefixes = self.withdraw or []

        if self.announce:
            for route_data in self.announce:
                try:
                    attrs_data = route_data["attrs"]
                    attributes = AGPRouteAttributes(
                        path=attrs_data["path"],
                        next_hop=attrs_data["next_hop"],
                        originator_id=attrs_data.get("originator_id"),
                        cluster_list=attrs_data.get("cluster_list"),
                        local_pref=attrs_data.get("local_pref"),
                        med=attrs_data.get("med"),
                        qos_supported=attrs_data.get("qos_supported"),
                        capacity=attrs_data.get("capacity"),
                        health=attrs_data.get("health"),
                        cost=attrs_data.get("cost"),
                        predictability=attrs_data.get("predictability"),
                        communities=attrs_data.get("communities"),
                        security_groups=attrs_data.get("security_groups"),
                        regions=attrs_data.get("regions"),
                        valid_until=attrs_data.get("valid_until"),
                    )

                    route = AGPRoute(
                        prefix=route_data["prefix"],
                        attributes=attributes,
                        received_at=time.time(),
                        peer_router_id=peer_router_id,
                    )

                    announced_routes.append(route)

                except (KeyError, ValidationError) as e:
                    # Log error but continue processing other routes
                    error_msg = str(e)
                    if "QoS" in error_msg:
                        # This is a policy error, but we don't have access to the route table here
                        # The metrics will be handled by the caller
                        pass
                    elif "no-export" in error_msg:
                        # This is a policy error, but we don't have access to the route table here
                        # The metrics will be handled by the caller
                        pass
                    else:
                        # Non-policy validation error
                        pass
                    print(f"Failed to parse route {route_data.get('prefix', 'unknown')}: {e}")

        return announced_routes, withdrawn_prefixes

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AGPUpdateMessage:
        """Create UPDATE message from dictionary, ignoring unknown fields."""
        # Extract known fields, ignore unknown ones for backward compatibility
        known_fields = {
            "type": data.get("type", AGPMessageType.UPDATE.value),
            "announce": data.get("announce"),
            "withdraw": data.get("withdraw"),
        }

        return cls(**known_fields)


@dataclass
class AGPOpenMessage:
    """AGP OPEN message structure for version negotiation."""

    type: str = AGPMessageType.OPEN.value
    router_id: str = ""
    adn: int = 0
    capabilities: dict[str, Any] = None

    def __post_init__(self):
        """Initialize capabilities dict if None."""
        if self.capabilities is None:
            self.capabilities = {}

    def validate(self) -> None:
        """Validate OPEN message structure."""
        if self.type != AGPMessageType.OPEN.value:
            raise ValidationError(f"Invalid message type: {self.type}")

        if not self.router_id:
            raise ValidationError("router_id is required")

        if not isinstance(self.adn, int) or self.adn < 0 or self.adn > 0xFFFFFFFF:
            raise ValidationError(f"Invalid ADN: {self.adn}")

        if not isinstance(self.capabilities, dict):
            raise ValidationError("capabilities must be a dictionary")

    def get_agp_version(self) -> str:
        """Get AGP version from capabilities."""
        return self.capabilities.get("agp_version", "1.0")

    def is_version_compatible(self, our_version: str = "1.0") -> bool:
        """Check if peer version is compatible with ours."""
        peer_version = self.get_agp_version()

        # Simple version compatibility check
        # For now, assume major version compatibility
        try:
            our_major = int(our_version.split(".")[0])
            peer_major = int(peer_version.split(".")[0])
            return our_major == peer_major
        except (ValueError, IndexError):
            return False

    def negotiate_version(self, our_version: str = "1.0") -> str:
        """Negotiate AGP version with peer."""
        if self.is_version_compatible(our_version):
            return min(our_version, self.get_agp_version())
        else:
            raise ValidationError(f"Incompatible AGP version: peer={self.get_agp_version()}, ours={our_version}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AGPOpenMessage:
        """Create OPEN message from dictionary, ignoring unknown fields."""
        # Extract known fields, ignore unknown ones for backward compatibility
        known_fields = {
            "type": data.get("type", AGPMessageType.OPEN.value),
            "router_id": data.get("router_id", ""),
            "adn": data.get("adn", 0),
            "capabilities": data.get("capabilities", {}),
        }

        return cls(**known_fields)


class AGPRouteTable:
    """AGP route table for storing and managing routes."""

    def __init__(self, config: RouteSelectionConfig | None = None, safe_mode_config: SafeModeConfig | None = None):
        self.routes: dict[str, dict[str, AGPRoute]] = {}  # prefix -> peer_id -> route
        self.config = config or RouteSelectionConfig()
        self.config.validate()  # Validate configuration

        # Initialize safe mode configuration
        self.safe_mode_config = safe_mode_config or SafeModeConfig()
        self.safe_mode_config.validate()
        self.safe_mode_active = False

        # Initialize dampening tracker with default config
        dampening_config = RouteDampeningConfig()
        hysteresis_config = HysteresisConfig()
        hold_down_config = HoldDownConfig()
        self.dampening_tracker = RouteDampeningTracker(dampening_config, hysteresis_config, hold_down_config)

        self.routes_active = REGISTRY.gauge("agp_routes_active")
        self.route_updates_total = REGISTRY.counter("agp_route_updates_total")
        self.route_withdrawals_total = REGISTRY.counter("agp_route_withdrawals_total")
        self.ecmp_splits_total = REGISTRY.counter("agp_ecmp_splits_total")
        self.routes_dampened = REGISTRY.gauge("agp_routes_dampened")
        self.route_snapshots_taken_total = REGISTRY.counter("agp_route_snapshots_taken_total")
        self.stale_health_routes_total = REGISTRY.gauge("agp_stale_health_routes_total")
        self.flaps_dampened_total = REGISTRY.counter("agp_flaps_dampened_total")
        self.hold_down_events_total = REGISTRY.counter("agp_hold_down_events_total")
        self.safe_mode_entries_total = REGISTRY.counter("agp_safe_mode_entries_total")
        self.backpressure_capacity_reductions_total = REGISTRY.counter("agp_backpressure_capacity_reductions_total")
        self.qos_fit_rejections_total = REGISTRY.counter("agp_qos_fit_rejections_total")
        self.no_export_filtered_total = REGISTRY.counter("agp_no_export_filtered_total")
        self.health_suppressed_updates_total = REGISTRY.counter("agp_health_suppressed_updates_total")
        self.attestation_rejections_total = REGISTRY.counter("agp_attestation_rejections_total")

    def update_routes(self, routes: list[AGPRoute]) -> None:
        """Update routes in the table."""
        for route in routes:
            if route.prefix not in self.routes:
                self.routes[route.prefix] = {}

            # Apply backpressure capacity reduction if active
            backpressure_status = GLOBAL_AGENT_STATUS.get_backpressure_status()
            if backpressure_status["backpressure_active"] and route.attributes.capacity:
                # Apply capacity reduction factor to all capacity metrics
                reduction_factor = backpressure_status["capacity_reduction_factor"]
                original_capacity = route.attributes.capacity.copy()

                route.attributes.capacity = {
                    "max_parallel": int(original_capacity["max_parallel"] * reduction_factor),
                    "tokens_per_s": int(original_capacity["tokens_per_s"] * reduction_factor),
                    "usd_per_s": original_capacity["usd_per_s"] * reduction_factor,
                }

                # Track backpressure capacity reductions
                self.backpressure_capacity_reductions_total.inc()

            # Record dampening event for route advertisement
            was_suppressed_before = self.dampening_tracker.is_suppressed(route.prefix)
            self.dampening_tracker.record_route_change(route.prefix, is_withdrawal=False)
            is_suppressed_after = self.dampening_tracker.is_suppressed(route.prefix)

            # Track if this route advertisement was dampened
            if is_suppressed_after and not was_suppressed_before:
                self.flaps_dampened_total.inc()

            self.routes[route.prefix][route.peer_router_id] = route
            self.route_updates_total.inc()

        self._update_metrics()

    def withdraw_routes(self, prefixes: list[str], peer_router_id: str | None = None) -> None:
        """Withdraw routes from the table."""
        for prefix in prefixes:
            # Record dampening event for route withdrawal
            was_suppressed_before = self.dampening_tracker.is_suppressed(prefix)
            self.dampening_tracker.record_route_change(prefix, is_withdrawal=True)
            is_suppressed_after = self.dampening_tracker.is_suppressed(prefix)

            # Track if this route withdrawal was dampened
            if is_suppressed_after and not was_suppressed_before:
                self.flaps_dampened_total.inc()

            if prefix in self.routes:
                if peer_router_id:
                    # Withdraw specific peer's route
                    if peer_router_id in self.routes[prefix]:
                        del self.routes[prefix][peer_router_id]
                        self.route_withdrawals_total.inc()
                        if not self.routes[prefix]:
                            del self.routes[prefix]
                else:
                    # Withdraw all routes for prefix
                    del self.routes[prefix]
                    self.route_withdrawals_total.inc()

        self._update_metrics()

    def update_routes_health_based(self, routes: list[AGPRoute], health_degraded: bool) -> None:
        """Update routes with health-based hold-down/grace period logic."""
        for route in routes:
            if route.prefix not in self.routes:
                self.routes[route.prefix] = {}

            # Apply backpressure capacity reduction if active
            backpressure_status = GLOBAL_AGENT_STATUS.get_backpressure_status()
            if backpressure_status["backpressure_active"] and route.attributes.capacity:
                # Apply capacity reduction factor to all capacity metrics
                reduction_factor = backpressure_status["capacity_reduction_factor"]
                original_capacity = route.attributes.capacity.copy()

                route.attributes.capacity = {
                    "max_parallel": int(original_capacity["max_parallel"] * reduction_factor),
                    "tokens_per_s": int(original_capacity["tokens_per_s"] * reduction_factor),
                    "usd_per_s": original_capacity["usd_per_s"] * reduction_factor,
                }

                # Track backpressure capacity reductions
                self.backpressure_capacity_reductions_total.inc()

            # Record health change for hold-down/grace period tracking
            self.dampening_tracker.record_health_change(route.prefix, health_degraded)

            # Check if advertisement should be delayed due to grace period
            if not health_degraded and self.dampening_tracker.should_delay_advertisement(route.prefix):
                self.hold_down_events_total.inc()
                continue  # Skip advertisement during grace period

            # Record dampening event for route advertisement
            was_suppressed_before = self.dampening_tracker.is_suppressed(route.prefix)
            self.dampening_tracker.record_route_change(route.prefix, is_withdrawal=False)
            is_suppressed_after = self.dampening_tracker.is_suppressed(route.prefix)

            # Track if this route advertisement was dampened
            if is_suppressed_after and not was_suppressed_before:
                self.flaps_dampened_total.inc()

            self.routes[route.prefix][route.peer_router_id] = route
            self.route_updates_total.inc()

        self._update_metrics()

    def withdraw_routes_health_based(
        self, prefixes: list[str], peer_router_id: str | None = None, health_degraded: bool = True
    ) -> None:
        """Withdraw routes with health-based hold-down logic."""
        for prefix in prefixes:
            # Record health change for hold-down tracking
            self.dampening_tracker.record_health_change(prefix, health_degraded)

            # Check if withdrawal should be delayed due to hold-down period
            if health_degraded and self.dampening_tracker.should_delay_withdrawal(prefix):
                self.hold_down_events_total.inc()
                continue  # Skip withdrawal during hold-down period

            # Record dampening event for route withdrawal
            was_suppressed_before = self.dampening_tracker.is_suppressed(prefix)
            self.dampening_tracker.record_route_change(prefix, is_withdrawal=True)
            is_suppressed_after = self.dampening_tracker.is_suppressed(prefix)

            # Track if this route withdrawal was dampened
            if is_suppressed_after and not was_suppressed_before:
                self.flaps_dampened_total.inc()

            if prefix in self.routes:
                if peer_router_id:
                    # Withdraw specific peer's route
                    if peer_router_id in self.routes[prefix]:
                        del self.routes[prefix][peer_router_id]
                        self.route_withdrawals_total.inc()
                        if not self.routes[prefix]:
                            del self.routes[prefix]
                else:
                    # Withdraw all routes for prefix
                    del self.routes[prefix]
                    self.route_withdrawals_total.inc()

        self._update_metrics()

    def get_routes(self, prefix: str) -> list[AGPRoute]:
        """Get all routes for a prefix."""
        if prefix not in self.routes:
            return []
        return list(self.routes[prefix].values())

    def get_best_route(self, prefix: str) -> AGPRoute | None:
        """Get the best route for a prefix using weighted path selection algorithm."""
        # Check if prefix is suppressed due to dampening
        if self.dampening_tracker.is_suppressed(prefix):
            return None

        candidates = self.get_routes(prefix)
        if not candidates:
            return None

        # Filter valid routes
        valid_candidates = [r for r in candidates if r.is_valid()]
        if not valid_candidates:
            return None

        # Score all candidates
        scored_candidates = [(route, self._calculate_route_score(route)) for route in valid_candidates]

        # Sort by score (lower is better)
        scored_candidates.sort(key=lambda x: x[1])

        # Return best route
        return scored_candidates[0][0]

    def get_ecmp_routes(self, prefix: str, requested_qqos: str | None = None) -> list[AGPRoute]:
        """Get ECMP routes for a prefix using weighted selection and hashing."""
        # Check if prefix is suppressed due to dampening
        if self.dampening_tracker.is_suppressed(prefix):
            return []

        candidates = self.get_routes(prefix)
        if not candidates:
            return []

        # Filter valid routes and apply QoS policy filter
        valid_candidates = [r for r in candidates if r.is_valid()]

        if requested_qqos and valid_candidates:
            # Filter routes that support the requested QoS
            valid_candidates = [
                r
                for r in valid_candidates
                if r.attributes.qos_supported and requested_qqos in r.attributes.qos_supported
            ]

        if not valid_candidates:
            return []

        # Score all candidates
        scored_candidates = [(route, self._calculate_route_score(route)) for route in valid_candidates]

        # Group by score (equal cost)
        score_groups = {}
        for route, score in scored_candidates:
            rounded_score = round(score, 6)  # Handle floating point precision
            if rounded_score not in score_groups:
                score_groups[rounded_score] = []
            score_groups[rounded_score].append(route)

        # Get the best score group
        if not score_groups:
            return []

        best_score = min(score_groups.keys())
        best_routes = score_groups[best_score]

        # Apply ECMP limit
        if len(best_routes) > self.config.max_ecmp_paths:
            best_routes = best_routes[: self.config.max_ecmp_paths]

        # Update ECMP metrics
        if len(best_routes) > 1:
            self.ecmp_splits_total.inc()

        return best_routes

    def _calculate_route_score(self, route: AGPRoute) -> float:
        """Calculate weighted score for route selection."""
        score = 0.0

        # LOCAL_PREF (higher is better, so we negate)
        local_pref = route.attributes.local_pref or 0
        score += self.config.local_pref_weight * (-local_pref / 1000.0)  # Normalize

        # Path Length (shorter is better)
        path_len = len(route.attributes.path)
        score += self.config.path_len_weight * (path_len / 10.0)  # Normalize

        # Health Score (lower p95 + err_rate is better)
        health_score = 0.0
        if route.attributes.health:
            p95_ms = route.attributes.health.get("p95_ms", 1000)
            err_rate = route.attributes.health.get("err_rate", 0.1)
            base_health_score = (p95_ms / 1000.0) + (err_rate * 10)  # Normalize and combine

            # Apply freshness multiplier F = exp(-Δt / τ)
            freshness_factor = self._calculate_freshness_factor(route)
            health_score = base_health_score / freshness_factor  # Higher freshness = lower score (better)
        score += self.config.health_weight * health_score

        # Cost Score (lower cost is better)
        cost_score = 0.0
        if route.attributes.cost:
            usd_per_1k = route.attributes.cost.get("usd_per_1k_tokens", 0.01)
            cost_score = usd_per_1k * 100  # Normalize
        score += self.config.cost_weight * cost_score

        # Predictability Bonus (lower MAPE + under_rate is better)
        predict_score = 0.0
        if route.attributes.predictability:
            mape = route.attributes.predictability.get("estimate_mape_7d", 0.2)
            under_rate = route.attributes.predictability.get("under_rate_7d", 0.1)
            predict_score = mape + under_rate  # Combine
        score += self.config.predict_weight * predict_score

        # QoS Fit (binary: 0 for fit, 1 for no fit)
        qos_score = 0.0  # Assume fit by default
        # This would be calculated based on requested QoS vs supported QoS
        score += self.config.qos_fit_weight * qos_score

        # Overhead calibration penalty (GAP-109C)
        overhead_score = 0.0
        if route.attributes.overhead:
            mape_7d = route.attributes.overhead.get("overhead_mape_7d", 0.0)
            p95_factor = route.attributes.overhead.get("overhead_p95_factor", 1.0)
            # Penalize routes with poor overhead prediction accuracy
            # Higher MAPE = worse prediction, higher penalty
            # p95_factor > 1.0 means over-estimation (wasted budget), < 1.0 means under-estimation (risk)
            overhead_score = mape_7d + abs(p95_factor - 1.0)
        score += self.config.overhead_weight * overhead_score

        return score

    def _calculate_freshness_factor(self, route: AGPRoute) -> float:
        """Calculate freshness factor F = exp(-Δt / τ) for health metrics."""
        import math

        if not route.attributes.health:
            return 1.0  # No penalty for routes without health metrics

        metrics_timestamp = route.attributes.health.get("metrics_timestamp")
        if not metrics_timestamp:
            return 1.0  # No penalty if no timestamp

        # Get half-life from health metrics or use default
        tau = route.attributes.health.get("metrics_half_life_s", 30.0)  # Default 30 seconds

        # Calculate time difference
        current_time = time.time()
        delta_t = current_time - metrics_timestamp

        if delta_t <= 0:
            return 1.0  # Future timestamps get no penalty

        # Calculate freshness factor F = exp(-Δt / τ)
        freshness_factor = math.exp(-delta_t / tau)

        # Ensure minimum freshness to prevent division by very small numbers
        return max(freshness_factor, 0.1)

    def select_route_with_ecmp(
        self, prefix: str, session_id: str, requested_qqos: str | None = None
    ) -> AGPRoute | None:
        """Select a route using ECMP hashing for load balancing."""
        ecmp_routes = self.get_ecmp_routes(prefix, requested_qqos)

        if not ecmp_routes:
            return None

        if len(ecmp_routes) == 1:
            return ecmp_routes[0]

        # Use session_id for consistent hashing
        hash_input = f"{self.config.ecmp_hash_seed}:{session_id}:{prefix}"
        hash_value = hash(hash_input) % len(ecmp_routes)

        return ecmp_routes[hash_value]

    def cleanup_expired(self) -> int:
        """Clean up expired routes. Returns number of routes removed."""
        removed = 0
        prefixes_to_remove = []

        for prefix, peer_routes in self.routes.items():
            peers_to_remove = []
            for peer_id, route in peer_routes.items():
                if not route.is_valid():
                    peers_to_remove.append(peer_id)
                    removed += 1

            for peer_id in peers_to_remove:
                del peer_routes[peer_id]

            if not peer_routes:
                prefixes_to_remove.append(prefix)

        for prefix in prefixes_to_remove:
            del self.routes[prefix]

        if removed > 0:
            self._update_metrics()

        return removed

    def _update_metrics(self) -> None:
        """Update route count metrics."""
        total_routes = sum(len(peer_routes) for peer_routes in self.routes.values())
        self.routes_active.set(total_routes)

        # Count suppressed prefixes
        suppressed_count = sum(1 for prefix in self.routes.keys() if self.dampening_tracker.is_suppressed(prefix))
        self.routes_dampened.set(suppressed_count)

        # Count stale health routes
        stale_count = self._count_stale_health_routes()
        self.stale_health_routes_total.set(stale_count)

    def _count_stale_health_routes(self) -> int:
        """Count routes with stale health metrics."""
        stale_count = 0
        current_time = time.time()

        for _prefix, peer_routes in self.routes.items():
            for route in peer_routes.values():
                if route.attributes.health:
                    metrics_timestamp = route.attributes.health.get("metrics_timestamp")
                    if metrics_timestamp:
                        delta_t = current_time - metrics_timestamp
                        # Consider stale if older than 5 minutes (300 seconds)
                        if delta_t > 300:
                            stale_count += 1

        return stale_count

    def get_stats(self) -> dict[str, Any]:
        """Get route table statistics."""
        total_prefixes = len(self.routes)
        total_routes = sum(len(peer_routes) for peer_routes in self.routes.values())

        return {
            "total_prefixes": total_prefixes,
            "total_routes": total_routes,
            "routes_per_prefix_avg": total_routes / total_prefixes if total_prefixes > 0 else 0,
        }

    def get_dampening_info(self, prefix: str) -> dict[str, Any]:
        """Get dampening information for a prefix."""
        return self.dampening_tracker.get_dampening_info(prefix)

    def cleanup_dampening_states(self) -> None:
        """Clean up expired dampening states."""
        self.dampening_tracker.cleanup_expired_states()

    def take_snapshot(self) -> dict[str, Any]:
        """Take a snapshot of the current route table state."""
        snapshot = {"timestamp": time.time(), "routes": {}, "dampening_states": {}, "stats": self.get_stats()}

        # Serialize routes
        for prefix, peer_routes in self.routes.items():
            snapshot["routes"][prefix] = {}
            for peer_id, route in peer_routes.items():
                snapshot["routes"][prefix][peer_id] = route.to_dict()

        # Serialize dampening states
        for prefix in self.routes.keys():
            dampening_info = self.dampening_tracker.get_dampening_info(prefix)
            if dampening_info["penalty"] > 0:  # Only save non-zero penalty states
                snapshot["dampening_states"][prefix] = dampening_info

        self.route_snapshots_taken_total.inc()
        return snapshot

    def restore_from_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Restore route table state from a snapshot."""
        # Clear current state
        self.routes.clear()
        self.dampening_tracker.clear_all_states()

        # Restore routes
        for prefix, peer_routes in snapshot.get("routes", {}).items():
            self.routes[prefix] = {}
            for peer_id, route_dict in peer_routes.items():
                route = AGPRoute.from_dict(route_dict)
                self.routes[prefix][peer_id] = route

        # Restore dampening states
        for prefix, dampening_info in snapshot.get("dampening_states", {}).items():
            self.dampening_tracker.restore_state(prefix, dampening_info)

        self._update_metrics()

    def diff_snapshots(self, snapshot1: dict[str, Any], snapshot2: dict[str, Any]) -> dict[str, Any]:
        """Compute diff between two snapshots."""
        diff = {"added_prefixes": [], "removed_prefixes": [], "modified_prefixes": [], "dampening_changes": []}

        routes1 = snapshot1.get("routes", {})
        routes2 = snapshot2.get("routes", {})

        # Find added prefixes
        for prefix in routes2.keys():
            if prefix not in routes1:
                diff["added_prefixes"].append(prefix)

        # Find removed prefixes
        for prefix in routes1.keys():
            if prefix not in routes2:
                diff["removed_prefixes"].append(prefix)

        # Find modified prefixes
        for prefix in routes1.keys():
            if prefix in routes2:
                peers1 = set(routes1[prefix].keys())
                peers2 = set(routes2[prefix].keys())
                if peers1 != peers2:
                    diff["modified_prefixes"].append(
                        {"prefix": prefix, "added_peers": list(peers2 - peers1), "removed_peers": list(peers1 - peers2)}
                    )

        # Check dampening changes
        dampening1 = snapshot1.get("dampening_states", {})
        dampening2 = snapshot2.get("dampening_states", {})

        for prefix in set(dampening1.keys()) | set(dampening2.keys()):
            penalty1 = dampening1.get(prefix, {}).get("penalty", 0)
            penalty2 = dampening2.get(prefix, {}).get("penalty", 0)
            if penalty1 != penalty2:
                diff["dampening_changes"].append({"prefix": prefix, "old_penalty": penalty1, "new_penalty": penalty2})

        return diff

    def enter_safe_mode(self) -> bool:
        """Enter safe mode by loading last-known-good snapshot. Returns True if successful."""
        if not self.safe_mode_config.enabled:
            return False

        try:
            if not os.path.exists(self.safe_mode_config.snapshot_path):
                print(f"Safe mode snapshot not found: {self.safe_mode_config.snapshot_path}")
                return False

            with open(self.safe_mode_config.snapshot_path, encoding="utf-8") as f:
                snapshot = json.load(f)

            self.restore_from_snapshot(snapshot)
            self.safe_mode_active = True
            self.safe_mode_entries_total.inc()

            print(f"Entered safe mode with snapshot: {self.safe_mode_config.snapshot_path}")
            return True

        except Exception as e:
            print(f"Failed to enter safe mode: {e}")
            return False

    def exit_safe_mode(self) -> None:
        """Exit safe mode."""
        self.safe_mode_active = False
        print("Exited safe mode")

    def is_in_safe_mode(self) -> bool:
        """Check if currently in safe mode."""
        return self.safe_mode_active

    def save_last_known_good_snapshot(self) -> None:
        """Save current state as last-known-good snapshot for safe mode fallback."""
        if not self.safe_mode_config.enabled:
            return

        try:
            snapshot = self.take_snapshot()

            # Ensure directory exists
            os.makedirs(os.path.dirname(self.safe_mode_config.snapshot_path), exist_ok=True)

            with open(self.safe_mode_config.snapshot_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)

            print(f"Saved last-known-good snapshot: {self.safe_mode_config.snapshot_path}")

        except Exception as e:
            print(f"Failed to save last-known-good snapshot: {e}")


class AGPUpdateHandler:
    """Handles AGP UPDATE messages and route management."""

    def __init__(self, route_table: AGPRouteTable, router_id: str, arbiter_max_usd: float = 0.10):
        self.route_table = route_table
        self.router_id = router_id
        self.arbiter_max_usd = arbiter_max_usd
        self.update_messages_processed = REGISTRY.counter("agp_update_messages_processed_total")
        self.update_parse_errors = REGISTRY.counter("agp_update_parse_errors_total")
        self.agp_loops_prevented = REGISTRY.counter("agp_loops_prevented_total")
        self.incompatible_updates_total = REGISTRY.counter("agp_incompatible_updates_total")

    def _would_create_loop(self, route: AGPRoute) -> bool:
        """Check if accepting this route would create a loop."""
        attrs = route.attributes

        # Check if originator_id equals self
        if attrs.originator_id == self.router_id:
            return True

        # Check if our cluster_id is in the cluster_list
        # For now, we'll assume the cluster_id is derived from router_id
        # In a real implementation, this would be configurable
        if attrs.cluster_list:
            # Simple cluster_id derivation: take second part after ':' separator
            parts = self.router_id.split(":")
            cluster_id = parts[1] if len(parts) > 1 else self.router_id
            if cluster_id in attrs.cluster_list:
                return True

        return False

    def _extract_asn_from_route(self, route: AGPRoute) -> int:
        """Extract ASN from route attributes for ARPKI validation.

        In a real implementation, this would parse the ASN from BGP-like
        attributes or route metadata. For now, we'll derive it from the
        originator_id or use a default.
        """
        # Try to extract ASN from originator_id (format: "asn:router_id")
        if route.attributes.originator_id:
            parts = route.attributes.originator_id.split(":")
            if len(parts) >= 2:
                try:
                    return int(parts[0])
                except ValueError:
                    pass

        # Fallback: use a default ASN (in production, this should be configurable)
        return 65000  # Private ASN range

    def handle_update(self, message: dict[str, Any], peer_router_id: str) -> tuple[list[AGPRoute], list[str]]:
        """Handle an AGP UPDATE message."""
        try:
            update_msg = AGPUpdateMessage(
                type=message.get("type", AGPMessageType.UPDATE.value),
                announce=message.get("announce"),
                withdraw=message.get("withdraw"),
            )

            update_msg.validate()
            announced_routes, withdrawn_prefixes = update_msg.parse_routes(peer_router_id)

            # Check for policy rejections during parsing
            expected_routes = len(message.get("announce", []))
            actual_routes = len(announced_routes)
            rejected_routes = expected_routes - actual_routes

            if rejected_routes > 0:
                # Some routes were rejected during parsing - check the message content
                # to determine the type of rejection
                for route_data in message.get("announce", []):
                    attrs = route_data.get("attrs", {})
                    communities = attrs.get("communities", [])
                    qos_supported = attrs.get("qos_supported", [])

                    if "no-export" in communities:
                        self.route_table.no_export_filtered_total.inc()
                    elif qos_supported and all(qos in ["bronze"] for qos in qos_supported):
                        self.route_table.qos_fit_rejections_total.inc()

            # Filter out routes that would create loops (GAP-109A)
            filtered_routes = []
            for route in announced_routes:
                if self._would_create_loop(route):
                    self.agp_loops_prevented.inc()
                    continue

                # GAP-109D: ARPKI Route Attestation Validation
                asn = self._extract_asn_from_route(route)
                attestation_data = message.get("attestation", {})

                if attestation_data and not validate_agp_route_attestation(route.prefix, asn, attestation_data):
                    # Attestation validation failed - reject the route
                    self.route_table.attestation_rejections_total.inc()
                    continue

                # Policy validation: QoS Fit and no-export enforcement
                try:
                    route.attributes.validate()
                except ValidationError as e:
                    error_msg = str(e)
                    if "QoS" in error_msg:
                        self.route_table.qos_fit_rejections_total.inc()
                    elif "no-export" in error_msg:
                        self.route_table.no_export_filtered_total.inc()
                    else:
                        self.update_parse_errors.inc()
                    continue  # Skip this route

                filtered_routes.append(route)

            # Update route table
            if filtered_routes:
                self.route_table.update_routes(filtered_routes)
            if withdrawn_prefixes:
                self.route_table.withdraw_routes(withdrawn_prefixes, peer_router_id)

            self.update_messages_processed.inc()
            return filtered_routes, withdrawn_prefixes

        except (ValidationError, KeyError, TypeError) as e:
            self.update_parse_errors.inc()
            raise ValidationError(f"Failed to process UPDATE message: {e}") from e

    def handle_open(self, message: dict[str, Any], our_version: str = "1.0") -> tuple[bool, str]:
        """Handle an AGP OPEN message and perform version negotiation.

        Returns (success, negotiated_version) tuple.
        """
        try:
            open_msg = AGPOpenMessage.from_dict(message)
            open_msg.validate()

            # Perform version negotiation
            negotiated_version = open_msg.negotiate_version(our_version)

            print(f"AGP OPEN: peer_version={open_msg.get_agp_version()}, negotiated={negotiated_version}")
            return True, negotiated_version

        except (ValidationError, KeyError, TypeError) as e:
            print(f"Failed to process OPEN message: {e}")
            return False, ""

    def handle_message_with_version_check(
        self, message: dict[str, Any], peer_router_id: str, negotiated_version: str = "1.0"
    ) -> tuple[list[AGPRoute], list[str]]:
        """Handle UPDATE message with version compatibility checks."""
        try:
            # Use from_dict to ignore unknown fields for backward compatibility
            update_msg = AGPUpdateMessage.from_dict(message)
            update_msg.validate()

            announced_routes, withdrawn_prefixes = update_msg.parse_routes(peer_router_id)

            # Check for policy rejections during parsing
            expected_routes = len(message.get("announce", []))
            actual_routes = len(announced_routes)
            rejected_routes = expected_routes - actual_routes

            if rejected_routes > 0:
                # Some routes were rejected during parsing - check the message content
                # to determine the type of rejection
                for route_data in message.get("announce", []):
                    attrs = route_data.get("attrs", {})
                    communities = attrs.get("communities", [])
                    qos_supported = attrs.get("qos_supported", [])

                    if "no-export" in communities:
                        self.route_table.no_export_filtered_total.inc()
                    elif qos_supported and all(qos in ["bronze"] for qos in qos_supported):
                        self.route_table.qos_fit_rejections_total.inc()

            # Filter out routes that would create loops (GAP-109A)
            filtered_routes = []
            for route in announced_routes:
                if self._would_create_loop(route):
                    self.agp_loops_prevented.inc()
                    continue

                # Policy validation: QoS Fit and no-export enforcement
                try:
                    route.attributes.validate()
                except ValidationError as e:
                    error_msg = str(e)
                    if "QoS" in error_msg:
                        self.route_table.qos_fit_rejections_total.inc()
                    elif "no-export" in error_msg:
                        self.route_table.no_export_filtered_total.inc()
                    else:
                        self.update_parse_errors.inc()
                    continue  # Skip this route

                filtered_routes.append(route)

            # Update route table
            if filtered_routes:
                self.route_table.update_routes(filtered_routes)
            if withdrawn_prefixes:
                self.route_table.withdraw_routes(withdrawn_prefixes, peer_router_id)

            self.update_messages_processed.inc()
            return filtered_routes, withdrawn_prefixes

        except (ValidationError, KeyError, TypeError) as e:
            # Check if this is a version incompatibility issue
            if "unknown" in str(e).lower() or "unexpected" in str(e).lower():
                self.incompatible_updates_total.inc()
                print(f"Incompatible UPDATE message from {peer_router_id}: {e}")
            else:
                self.update_parse_errors.inc()
            raise ValidationError(f"Failed to process UPDATE message: {e}") from e
