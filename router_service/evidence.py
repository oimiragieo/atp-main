"""POC: Evidence scorer (GAP-025) and self-consistency sampling (GAP-102).

Validates citations and provides self-consistency sampling for improved confidence.
"""

from __future__ import annotations

import logging
import re
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from metrics.registry import REGISTRY

logger = logging.getLogger(__name__)

_CTR_EVIDENCE_FAIL = REGISTRY.counter("evidence_fail_total")


@dataclass
class Citation:
    index: int
    source: str  # url or doc id


def validate_citations(text: str, citations: Sequence[Citation]) -> bool:
    markers = {int(m) for m in re.findall(r"\[(\d+)\]", text)}
    provided = {c.index for c in citations}
    ok = markers.issubset(provided)
    if not ok:
        _CTR_EVIDENCE_FAIL.inc(1)
    return ok


# ---- Self-Consistency Sampling (GAP-102) ----

_CTR_SELF_CONSISTENCY = REGISTRY.counter("self_consistency_invocations_total")


@dataclass
class ConsistencyResult:
    """Result of self-consistency sampling."""

    responses: list[str]
    consensus_score: float
    confidence_level: str  # "high", "medium", "low"
    best_response: str
    metadata: dict[str, Any]


class SelfConsistencySampler:
    """Controller for self-consistency sampling to improve response confidence.

    Runs multiple inferences with the same prompt and measures consistency
    to identify the most reliable response.
    """

    def __init__(self, num_samples: int = 3, temperature: float = 0.7):
        self.num_samples = num_samples
        self.temperature = temperature

    def sample_consistent_response(
        self, prompt: str, inference_fn: callable, similarity_threshold: float = 0.7
    ) -> ConsistencyResult:
        """Sample multiple responses and return the most consistent one.

        Args:
            prompt: The input prompt
            inference_fn: Function that takes a prompt and returns a response string
            similarity_threshold: Minimum similarity score for "high" confidence

        Returns:
            ConsistencyResult with consensus analysis
        """
        _CTR_SELF_CONSISTENCY.inc(1)

        # Generate multiple responses
        responses = []
        for _ in range(self.num_samples):
            try:
                response = inference_fn(prompt)
                responses.append(response)
            except Exception as e:
                logger.warning(f"Inference failed during self-consistency sampling: {e}")
                continue

        if not responses:
            return ConsistencyResult(
                responses=[],
                consensus_score=0.0,
                confidence_level="low",
                best_response="",
                metadata={"error": "no_responses"},
            )

        # Calculate pairwise similarities
        similarities = []
        for i in range(len(responses)):
            for j in range(i + 1, len(responses)):
                sim = self._calculate_similarity(responses[i], responses[j])
                similarities.append(sim)

        # Overall consensus score (average similarity)
        consensus_score = statistics.mean(similarities) if similarities else 0.0

        # Determine confidence level
        if consensus_score >= similarity_threshold:
            confidence_level = "high"
        elif consensus_score >= similarity_threshold * 0.6:
            confidence_level = "medium"
        else:
            confidence_level = "low"

        # Select best response (could be majority vote or highest similarity)
        best_response = self._select_best_response(responses, similarities)

        return ConsistencyResult(
            responses=responses,
            consensus_score=consensus_score,
            confidence_level=confidence_level,
            best_response=best_response,
            metadata={
                "num_samples": len(responses),
                "avg_similarity": consensus_score,
                "similarity_range": (min(similarities), max(similarities)) if similarities else (0, 0),
            },
        )

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts using Jaccard similarity on tokens."""
        tokens1 = set(text1.lower().split())
        tokens2 = set(text2.lower().split())

        if not tokens1 and not tokens2:
            return 1.0
        if not tokens1 or not tokens2:
            return 0.0

        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)
        return intersection / union if union > 0 else 0.0

    def _select_best_response(self, responses: list[str], similarities: list[float]) -> str:
        """Select the best response from the set.

        For now, uses a simple approach: return the most common response,
        or the first one if all are different.
        """
        if len(responses) == 1:
            return responses[0]

        # Count frequency of each response
        response_counts = {}
        for resp in responses:
            # Normalize whitespace for comparison
            normalized = " ".join(resp.split())
            response_counts[normalized] = response_counts.get(normalized, 0) + 1

        # Return the most frequent response
        most_common = max(response_counts.items(), key=lambda x: x[1])
        return most_common[0]
