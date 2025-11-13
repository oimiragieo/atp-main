"""Shared constants for routing functionality."""

from dataclasses import dataclass


@dataclass
class Candidate:
    name: str
    cost_per_1k_tokens: float
    quality_pred: float  # 0-1
    latency_p95: int  # ms
    region: str = "us-west"  # Default region


# Static catalog (would be external/configured)
CATALOG = [
    Candidate("cheap-model", 0.4, 0.70, 900, "us-west"),
    # Experimental model starts as shadow (status in registry governs use in plan)
    Candidate("exp-model", 0.8, 0.78, 950, "us-east"),
    Candidate("mid-model", 1.0, 0.80, 1100, "eu-west"),
    Candidate("premium-model", 2.0, 0.90, 1400, "asia-east"),
]

QUALITY_THRESH = {"fast": 0.60, "balanced": 0.75, "high": 0.85}
