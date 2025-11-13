"""Cost tracking for tool use and agent conversations.

Implements Claude SDK cost tracking patterns:
- Token usage tracking (input, output, cache)
- Message ID deduplication
- Step-based accounting
- USD cost calculation
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Usage:
    """Token usage metrics."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    service_tier: str = "default"


@dataclass
class CostMetrics:
    """Cost calculation metrics."""

    # Token pricing (per million tokens)
    INPUT_TOKEN_PRICE = 3.00  # $3 per 1M tokens (Sonnet 3.5)
    OUTPUT_TOKEN_PRICE = 15.00  # $15 per 1M tokens
    CACHE_WRITE_PRICE = 3.75  # $3.75 per 1M tokens
    CACHE_READ_PRICE = 0.30  # $0.30 per 1M tokens

    @classmethod
    def calculate_cost(cls, usage: Usage) -> float:
        """Calculate total cost in USD.

        Args:
            usage: Token usage metrics

        Returns:
            Total cost in USD
        """
        input_cost = (usage.input_tokens / 1_000_000) * cls.INPUT_TOKEN_PRICE
        output_cost = (usage.output_tokens / 1_000_000) * cls.OUTPUT_TOKEN_PRICE
        cache_write_cost = (usage.cache_creation_input_tokens / 1_000_000) * cls.CACHE_WRITE_PRICE
        cache_read_cost = (usage.cache_read_input_tokens / 1_000_000) * cls.CACHE_READ_PRICE

        return input_cost + output_cost + cache_write_cost + cache_read_cost


@dataclass
class ConversationStep:
    """Single step in a conversation."""

    step_id: str
    message_id: str  # For deduplication
    usage: Usage
    cost_usd: float
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class CostTracker:
    """Tracks costs across conversations."""

    def __init__(self):
        """Initialize cost tracker."""
        self._steps: list[ConversationStep] = []
        self._processed_messages: set[str] = set()  # For deduplication
        self._session_costs: dict[str, float] = {}  # session_id -> total cost

    def track_step(
        self,
        step_id: str,
        message_id: str,
        usage: Usage,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> float:
        """Track a conversation step.

        Implements deduplication: "All messages with the same id field
        report identical usage, so skip previously encountered IDs."

        Args:
            step_id: Unique step identifier
            message_id: Message ID for deduplication
            usage: Token usage metrics
            session_id: Optional session identifier
            metadata: Optional metadata

        Returns:
            Cost for this step in USD
        """
        # Deduplication: skip if we've seen this message ID
        if message_id in self._processed_messages:
            logger.debug(f"Skipping duplicate message: {message_id}")
            return 0.0

        # Calculate cost
        cost_usd = CostMetrics.calculate_cost(usage)

        # Create step
        step = ConversationStep(
            step_id=step_id,
            message_id=message_id,
            usage=usage,
            cost_usd=cost_usd,
            metadata=metadata or {},
        )

        # Track
        self._steps.append(step)
        self._processed_messages.add(message_id)

        # Update session cost
        if session_id:
            self._session_costs[session_id] = self._session_costs.get(session_id, 0.0) + cost_usd

        logger.info(f"Tracked step {step_id}: ${cost_usd:.4f} ({usage.input_tokens} in, {usage.output_tokens} out)")

        return cost_usd

    def get_session_cost(self, session_id: str) -> float:
        """Get total cost for a session."""
        return self._session_costs.get(session_id, 0.0)

    def get_total_cost(self) -> float:
        """Get total cost across all sessions."""
        return sum(step.cost_usd for step in self._steps)

    def get_total_tokens(self) -> dict[str, int]:
        """Get total token usage."""
        total = Usage()
        for step in self._steps:
            total.input_tokens += step.usage.input_tokens
            total.output_tokens += step.usage.output_tokens
            total.cache_creation_input_tokens += step.usage.cache_creation_input_tokens
            total.cache_read_input_tokens += step.usage.cache_read_input_tokens

        return {
            "input_tokens": total.input_tokens,
            "output_tokens": total.output_tokens,
            "cache_creation_input_tokens": total.cache_creation_input_tokens,
            "cache_read_input_tokens": total.cache_read_input_tokens,
            "total_tokens": total.input_tokens
            + total.output_tokens
            + total.cache_creation_input_tokens
            + total.cache_read_input_tokens,
        }

    def get_report(self) -> dict[str, Any]:
        """Generate cost report."""
        return {
            "total_steps": len(self._steps),
            "total_cost_usd": self.get_total_cost(),
            "tokens": self.get_total_tokens(),
            "sessions": len(self._session_costs),
            "session_costs": dict(self._session_costs),
        }

    def reset(self) -> None:
        """Reset all tracking data."""
        self._steps.clear()
        self._processed_messages.clear()
        self._session_costs.clear()


# Global tracker instance
_global_tracker = CostTracker()


def get_cost_tracker() -> CostTracker:
    """Get the global cost tracker."""
    return _global_tracker
