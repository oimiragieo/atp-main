# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Observation domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Observation:
    """
    Observation of an LLM request/response.

    Tracks performance, cost, and quality metrics.
    """

    request_id: str
    model: str
    latency_ms: float
    cost_usd: float | None = None
    quality_score: float | None = None
    tokens: int | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
            "quality_score": self.quality_score,
            "tokens": self.tokens,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Observation:
        """Create from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)

        return cls(
            request_id=data["request_id"],
            model=data["model"],
            latency_ms=data["latency_ms"],
            cost_usd=data.get("cost_usd"),
            quality_score=data.get("quality_score"),
            tokens=data.get("tokens"),
            timestamp=timestamp or datetime.now(),
            metadata=data.get("metadata", {}),
        )
