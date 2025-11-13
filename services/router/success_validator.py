"""Success metric integration & validators for GAP-205."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from metrics.registry import REGISTRY


class ValidationResult:
    """Result of a success/quality validation."""

    def __init__(
        self, format_ok: bool, safety_ok: bool, quality_score: float, details: Optional[dict[str, Any]] = None
    ):
        self.format_ok = format_ok
        self.safety_ok = safety_ok
        self.quality_score = quality_score
        self.details = details or {}

    @property
    def success(self) -> bool:
        """Overall success based on format and safety checks."""
        return self.format_ok and self.safety_ok


class SuccessValidator(ABC):
    """Abstract base class for success/quality validators."""

    @abstractmethod
    def validate_response(self, response_text: str, prompt: str, model_name: str, **kwargs) -> ValidationResult:
        """Validate a model response for success metrics.

        Args:
            response_text: The model's response text
            prompt: The original prompt
            model_name: Name of the model that generated the response
            **kwargs: Additional context (conversation_id, tenant, etc.)

        Returns:
            ValidationResult with format_ok, safety_ok, quality_score
        """
        pass


class BaselineQualityScorer(SuccessValidator):
    """Baseline quality scorer with simple heuristics."""

    def __init__(self):
        # Initialize metrics for GAP-205
        self._model_success_rate = REGISTRY.gauge("atp_model_success_rate")
        self._quality_score_avg = REGISTRY.gauge("atp_quality_score_avg")
        self._validation_count = REGISTRY.counter("atp_validations_total")

    def validate_response(self, response_text: str, prompt: str, model_name: str, **kwargs) -> ValidationResult:
        """Validate response using baseline heuristics."""

        # Format validation - check for basic structure
        format_ok = self._check_format(response_text)

        # Safety validation - check for harmful content patterns
        safety_ok = self._check_safety(response_text)

        # Quality scoring - simple heuristic based on length, coherence, etc.
        quality_score = self._calculate_quality_score(response_text, prompt)

        # Update metrics
        self._validation_count.inc()
        success_rate = 1.0 if (format_ok and safety_ok) else 0.0
        self._model_success_rate.set(success_rate)
        self._quality_score_avg.set(quality_score)

        details = {
            "model": model_name,
            "response_length": len(response_text),
            "prompt_length": len(prompt),
        }

        return ValidationResult(format_ok=format_ok, safety_ok=safety_ok, quality_score=quality_score, details=details)

    def _check_format(self, response_text: str) -> bool:
        """Check if response has proper format."""
        if not response_text or not response_text.strip():
            return False

        # Check minimum length (at least 10 characters for meaningful responses)
        if len(response_text.strip()) < 10:
            return False

        # Check for alphabetic characters (responses should contain some text)
        if not any(c.isalpha() for c in response_text):
            return False

        # Check for incomplete responses (ends with common cutoff patterns)
        cutoff_patterns = ["...", "/*", "def ", "class "]
        text_end = response_text.strip()[-10:].lower()  # Check last 10 chars
        for pattern in cutoff_patterns:
            if text_end.endswith(pattern.rstrip()):
                return False

        # Allow code blocks that are properly closed
        if "```" in response_text:
            # Count backticks - should be even number for complete blocks
            backtick_count = response_text.count("```")
            if backtick_count % 2 != 0:
                return False

        # Check for excessive repetition
        words = response_text.lower().split()
        if len(words) > 10:
            # Check if more than 30% of words are repeated
            unique_words = set(words)
            if len(unique_words) / len(words) < 0.7:
                return False

        return True

    def _check_safety(self, response_text: str) -> bool:
        """Check for potentially harmful content."""
        harmful_patterns = [
            "how to",
            "hack",
            "exploit",
            "illegal",
            "password",
            "credit card",
            "ssn",
            "kill",
            "harm",
            "violence",
            "terrorist",
            "cocaine",
            "heroin",
            "meth",
            "drug",
        ]

        response_lower = response_text.lower()
        for pattern in harmful_patterns:
            if pattern in response_lower:
                # Allow if it's clearly educational/safe context
                if not self._is_safe_context(response_lower, pattern):
                    return False

        return True

    def _is_safe_context(self, text: str, pattern: str) -> bool:
        """Check if harmful pattern appears in safe context."""
        safe_contexts = [
            "educational",
            "hypothetical",
            "fiction",
            "story",
            "movie",
            "book",
            "game",
            "historical",
            "programming",
            "coding",
            "python",
            "code",
            "write",
            "develop",
            "build",
            "create",
        ]

        # Look for safe context words within 100 characters of the pattern
        pattern_pos = text.find(pattern)
        if pattern_pos == -1:
            return True

        context_start = max(0, pattern_pos - 50)
        context_end = min(len(text), pattern_pos + len(pattern) + 50)
        context = text[context_start:context_end]

        return any(safe_word in context for safe_word in safe_contexts)

    def _calculate_quality_score(self, response_text: str, prompt: str) -> float:
        """Calculate quality score using simple heuristics."""
        score = 0.5  # Base score

        # Length appropriateness (responses should be reasonably sized)
        response_length = len(response_text)
        if 10 <= response_length <= 10000:
            score += 0.2
        elif response_length < 10:
            score -= 0.3
        elif response_length > 10000:
            score -= 0.1

        # Response diversity (avoid repetitive text)
        words = response_text.lower().split()
        if words:
            unique_ratio = len(set(words)) / len(words)
            score += min(0.2, unique_ratio * 0.3)

        # Basic coherence (has sentences, punctuation)
        sentence_count = response_text.count(".") + response_text.count("!") + response_text.count("?")
        if sentence_count > 0:
            avg_sentence_length = response_length / sentence_count
            if 10 <= avg_sentence_length <= 200:
                score += 0.1

        # Relevance heuristic (response mentions key prompt terms)
        prompt_words = set(prompt.lower().split())
        response_words = set(response_text.lower().split())
        overlap = len(prompt_words.intersection(response_words))
        if overlap > 0:
            relevance_score = min(0.2, overlap / len(prompt_words) * 0.4)
            score += relevance_score

        return max(0.0, min(1.0, score))
