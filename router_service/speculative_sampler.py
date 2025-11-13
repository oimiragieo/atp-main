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

"""Speculative Sampling Implementation (GAP-135).

This module implements speculative sampling with event surfacing for AI model inference,
providing structured observability for latency optimization decisions.
"""

from __future__ import annotations

import random
import time
from typing import Any

from router_service.event_emitter import SpeculativeEventType, emit_speculative_event


class SpeculativeSampler:
    """Implements speculative sampling for AI model inference with event tracking."""

    def __init__(
        self,
        draft_model: str = "draft-model-v1",
        target_model: str = "target-model-v1",
        acceptance_threshold: float = 0.7,
        draft_latency_ms: float = 10.0,
        target_latency_ms: float = 40.0,
    ):
        """Initialize speculative sampler.

        Args:
            draft_model: Name of the draft model
            target_model: Name of the target model
            acceptance_threshold: Minimum acceptance rate for speculation
            draft_latency_ms: Expected latency of draft model in milliseconds
            target_latency_ms: Expected latency of target model in milliseconds
        """
        self.draft_model = draft_model
        self.target_model = target_model
        self.acceptance_threshold = acceptance_threshold
        self.draft_latency_ms = draft_latency_ms
        self.target_latency_ms = target_latency_ms

        # Sample responses for simulation
        self.sample_responses = [
            "hello world",
            "good morning",
            "quick brown fox",
            "machine learning",
            "artificial intelligence"
        ]

    def _generate_draft_response(self, prompt: str) -> str:
        """Generate a draft response (simulated).

        Args:
            prompt: Input prompt

        Returns:
            Draft model response
        """
        # Simulate draft model inference
        time.sleep(self.draft_latency_ms / 1000.0)
        return random.choice(self.sample_responses)

    def _generate_target_response(self, prompt: str) -> str:
        """Generate target model response (simulated).

        Args:
            prompt: Input prompt

        Returns:
            Target model response
        """
        # Simulate target model inference
        time.sleep(self.target_latency_ms / 1000.0)
        base_response = random.choice(self.sample_responses)
        # Sometimes alter the response to simulate differences
        if random.random() < 0.3:
            words = base_response.split()
            if len(words) > 1:
                words[0] = words[0] + "_modified"
                return " ".join(words)
        return base_response

    def _calculate_confidence(self, draft: str, target: str) -> float:
        """Calculate confidence score for speculation acceptance.

        Args:
            draft: Draft model response
            target: Target model response

        Returns:
            Confidence score between 0.0 and 1.0
        """
        if not draft or not target:
            return 0.0

        # Simple prefix matching confidence
        draft_words = draft.split()
        target_words = target.split()

        if not draft_words or not target_words:
            return 0.0

        # Check if first word matches
        if draft_words[0] == target_words[0]:
            return 0.8  # High confidence for prefix match
        else:
            return 0.2  # Low confidence for mismatch

    def speculate(
        self,
        prompt: str,
        request_id: str | None = None
    ) -> dict[str, Any]:
        """Perform speculative sampling with event tracking.

        Args:
            prompt: Input prompt for inference
            request_id: Optional request identifier for tracking

        Returns:
            Dictionary containing inference results and metadata
        """
        start_time = time.time()

        # Emit speculation attempted event
        emit_speculative_event(
            SpeculativeEventType.SPECULATION_ATTEMPTED,
            self.draft_model,
            request_id=request_id,
            details={"prompt_length": len(prompt)}
        )

        # Generate draft response
        draft_start = time.time()
        draft_response = self._generate_draft_response(prompt)
        draft_latency = (time.time() - draft_start) * 1000.0

        # Generate target response
        target_start = time.time()
        target_response = self._generate_target_response(prompt)
        target_latency = (time.time() - target_start) * 1000.0

        # Calculate confidence
        confidence = self._calculate_confidence(draft_response, target_response)

        # Determine if speculation should be accepted
        accepted = confidence >= self.acceptance_threshold

        total_time = time.time() - start_time
        latency_saved = self.target_latency_ms - draft_latency if accepted else 0.0

        result = {
            "draft_response": draft_response,
            "target_response": target_response,
            "accepted": accepted,
            "confidence": confidence,
            "draft_latency_ms": draft_latency,
            "target_latency_ms": target_latency,
            "total_latency_ms": total_time * 1000.0,
            "latency_saved_ms": latency_saved,
            "effective_response": draft_response if accepted else target_response
        }

        # Emit appropriate event based on outcome
        if accepted:
            emit_speculative_event(
                SpeculativeEventType.SPECULATION_ACCEPTED,
                self.draft_model,
                latency_saved_ms=latency_saved,
                confidence_score=confidence,
                request_id=request_id,
                details={
                    "draft_response": draft_response,
                    "target_response": target_response,
                    "acceptance_threshold": self.acceptance_threshold
                }
            )
        else:
            emit_speculative_event(
                SpeculativeEventType.SPECULATION_REJECTED,
                self.draft_model,
                confidence_score=confidence,
                request_id=request_id,
                details={
                    "draft_response": draft_response,
                    "target_response": target_response,
                    "acceptance_threshold": self.acceptance_threshold
                }
            )

        return result

    def benchmark(self, trials: int = 100) -> dict[str, Any]:
        """Benchmark speculative sampling performance.

        Args:
            trials: Number of trials to run

        Returns:
            Benchmark results
        """
        total_saved = 0.0
        accepted_count = 0
        total_confidence = 0.0

        for i in range(trials):
            request_id = f"benchmark-{i}"
            result = self.speculate(f"Sample prompt {i}", request_id)

            if result["accepted"]:
                accepted_count += 1
                total_saved += result["latency_saved_ms"]

            total_confidence += result["confidence"]

        return {
            "trials": trials,
            "acceptance_rate": accepted_count / trials,
            "average_latency_saved_ms": total_saved / max(1, accepted_count),
            "average_confidence": total_confidence / trials,
            "total_speculative_events": trials
        }
