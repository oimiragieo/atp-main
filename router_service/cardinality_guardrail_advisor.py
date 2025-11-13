"""High-cardinality guardrail advisor for metrics monitoring.

This module implements GAP-367: High-cardinality guardrail advisor.
It monitors metrics for label explosion and provides recommendations to prevent
performance degradation from excessive cardinality.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass

from metrics.registry import REGISTRY

logger = logging.getLogger(__name__)

# GAP-367: High-cardinality guardrail advisor metrics
CARDINALITY_ALERTS_TOTAL = REGISTRY.counter("cardinality_alerts_total")
CARDINALITY_METRICS_MONITORED = REGISTRY.gauge("cardinality_metrics_monitored")
CARDINALITY_VIOLATIONS_ACTIVE = REGISTRY.gauge("cardinality_violations_active")


@dataclass
class CardinalityViolation:
    """Represents a cardinality violation for a metric."""
    metric_name: str
    unique_labels: int
    threshold: int
    timestamp: float
    sample_labels: list[str]  # Sample of problematic label values


@dataclass
class AdvisorRecommendation:
    """Recommendation from the cardinality advisor."""
    metric_name: str
    severity: str  # "low", "medium", "high", "critical"
    action: str
    rationale: str
    estimated_impact: str
    suggested_labels: list[str] | None = None


class CardinalityGuardrailAdvisor:
    """Advisor for monitoring and managing high-cardinality metrics.

    This class monitors metrics for cardinality explosions and provides
    actionable recommendations to prevent performance issues.
    """

    def __init__(
        self,
        warning_threshold: int = 100,
        critical_threshold: int = 1000,
        max_sample_labels: int = 10,
        alert_cooldown_seconds: int = 3600,  # 1 hour
    ):
        """Initialize the cardinality advisor.

        Args:
            warning_threshold: Number of unique labels that triggers warning
            critical_threshold: Number of unique labels that triggers critical alert
            max_sample_labels: Maximum number of sample labels to collect per violation
            alert_cooldown_seconds: Minimum time between alerts for same metric
        """
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.max_sample_labels = max_sample_labels
        self.alert_cooldown_seconds = alert_cooldown_seconds

        # Thread-safe storage
        self._lock = threading.RLock()
        self._metric_cardinality: dict[str, set[str]] = defaultdict(set)
        self._violations: dict[str, CardinalityViolation] = {}
        self._last_alert_time: dict[str, float] = {}

        # Track metrics being monitored
        self._monitored_metrics: set[str] = set()

        logger.info(
            f"Initialized cardinality advisor with thresholds: "
            f"warning={warning_threshold}, critical={critical_threshold}"
        )

    def record_label_value(self, metric_name: str, label_value: str) -> None:
        """Record a label value for cardinality tracking.

        Args:
            metric_name: Name of the metric
            label_value: Value of the label being tracked
        """
        with self._lock:
            self._metric_cardinality[metric_name].add(label_value)
            self._monitored_metrics.add(metric_name)

            # Update monitoring gauge
            CARDINALITY_METRICS_MONITORED.set(len(self._monitored_metrics))

            # Check for violations
            self._check_cardinality_violation(metric_name)

    def _check_cardinality_violation(self, metric_name: str) -> None:
        """Check if a metric has exceeded cardinality thresholds."""
        unique_labels = len(self._metric_cardinality[metric_name])

        # Determine severity
        if unique_labels >= self.critical_threshold:
            severity = "critical"
            threshold = self.critical_threshold
        elif unique_labels >= self.warning_threshold:
            severity = "warning"
            threshold = self.warning_threshold
        else:
            return  # No violation

        # Check alert cooldown
        now = time.time()
        last_alert = self._last_alert_time.get(metric_name, 0)
        if now - last_alert < self.alert_cooldown_seconds:
            return  # Too soon for another alert

        # Create violation record
        sample_labels = list(self._metric_cardinality[metric_name])[:self.max_sample_labels]
        violation = CardinalityViolation(
            metric_name=metric_name,
            unique_labels=unique_labels,
            threshold=threshold,
            timestamp=now,
            sample_labels=sample_labels
        )

        self._violations[metric_name] = violation
        self._last_alert_time[metric_name] = now

        # Update metrics
        CARDINALITY_ALERTS_TOTAL.inc()
        CARDINALITY_VIOLATIONS_ACTIVE.set(len(self._violations))

        logger.warning(
            f"Cardinality violation detected for metric '{metric_name}': "
            f"{unique_labels} unique labels (threshold: {threshold}, severity: {severity})"
        )

    def get_violations(self) -> list[CardinalityViolation]:
        """Get all current cardinality violations."""
        with self._lock:
            return list(self._violations.values())

    def get_recommendations(self) -> list[AdvisorRecommendation]:
        """Get advisor recommendations for current violations."""
        recommendations = []
        violations = self.get_violations()

        for violation in violations:
            rec = self._generate_recommendation(violation)
            if rec:
                recommendations.append(rec)

        return recommendations

    def _generate_recommendation(self, violation: CardinalityViolation) -> AdvisorRecommendation | None:
        """Generate a recommendation for a cardinality violation."""
        metric_name = violation.metric_name
        unique_labels = violation.unique_labels

        # Determine severity and action based on cardinality level
        if unique_labels >= self.critical_threshold * 2:
            severity = "critical"
            action = "Immediate action required: Implement label aggregation or sampling"
            rationale = (
                f"Metric has {unique_labels} unique labels, which is extremely high "
                "and may cause performance degradation, memory issues, or monitoring costs."
            )
            estimated_impact = "High risk of system instability and increased operational costs"
        elif unique_labels >= self.critical_threshold:
            severity = "high"
            action = "Review and optimize label usage for this metric"
            rationale = (
                f"Metric has {unique_labels} unique labels, exceeding the critical threshold "
                "of {violation.threshold}. This may impact query performance."
            )
            estimated_impact = "Moderate performance impact, potential for increased monitoring costs"
        elif unique_labels >= self.warning_threshold * 1.5:
            severity = "medium"
            action = "Consider aggregating similar labels or implementing rate limiting"
            rationale = (
                f"Metric has {unique_labels} unique labels, approaching critical levels. "
                "Monitor closely and plan optimization."
            )
            estimated_impact = "Minor performance impact, but trending toward concerning levels"
        else:
            severity = "low"
            action = "Monitor label growth and plan optimization if trend continues"
            rationale = (
                f"Metric has {unique_labels} unique labels, exceeding warning threshold "
                "but not yet critical."
            )
            estimated_impact = "Minimal current impact, but monitor growth rate"

        # Generate suggested label optimizations
        suggested_labels = self._suggest_label_optimizations(violation)

        return AdvisorRecommendation(
            metric_name=metric_name,
            severity=severity,
            action=action,
            rationale=rationale,
            estimated_impact=estimated_impact,
            suggested_labels=suggested_labels
        )

    def _suggest_label_optimizations(self, violation: CardinalityViolation) -> list[str] | None:
        """Suggest optimizations for high-cardinality labels."""
        sample_labels = violation.sample_labels

        if len(sample_labels) < 5:
            return None  # Not enough data for meaningful suggestions

        suggestions = []

        # Look for patterns in label values
        # Check for numeric patterns (contains digits)
        if any(any(char.isdigit() for char in label) for label in sample_labels):
            suggestions.append("Consider aggregating numeric IDs into ranges (e.g., 'user_1-1000')")

        if any(len(label) > 50 for label in sample_labels):
            suggestions.append("Long label values detected - consider truncating or hashing")

        if len({len(label) for label in sample_labels}) > 3:
            suggestions.append("Inconsistent label lengths suggest potential for standardization")

        # Check for common prefixes/suffixes
        prefixes = set()
        for label in sample_labels:
            if '_' in label:
                prefixes.add(label.split('_')[0])

        if len(prefixes) > 1:
            suggestions.append(f"Multiple prefixes detected ({', '.join(prefixes)}) - consider consistent naming")

        return suggestions if suggestions else None

    def get_cardinality_stats(self) -> dict[str, dict[str, int]]:
        """Get cardinality statistics for all monitored metrics."""
        with self._lock:
            return {
                metric: {
                    "unique_labels": len(labels),
                    "is_violation": metric in self._violations
                }
                for metric, labels in self._metric_cardinality.items()
            }

    def clear_violation(self, metric_name: str) -> bool:
        """Clear a violation for a metric (after remediation).

        Args:
            metric_name: Name of the metric

        Returns:
            True if violation was cleared, False if no violation existed
        """
        with self._lock:
            if metric_name in self._violations:
                del self._violations[metric_name]
                CARDINALITY_VIOLATIONS_ACTIVE.set(len(self._violations))
                logger.info(f"Cleared cardinality violation for metric '{metric_name}'")
                return True
            return False

    def reset_metric(self, metric_name: str) -> bool:
        """Reset cardinality tracking for a metric.

        Args:
            metric_name: Name of the metric

        Returns:
            True if metric was reset, False if not found
        """
        with self._lock:
            if metric_name in self._metric_cardinality:
                del self._metric_cardinality[metric_name]
                self._monitored_metrics.discard(metric_name)

                # Clear any violations
                self._violations.pop(metric_name, None)
                self._last_alert_time.pop(metric_name, None)

                CARDINALITY_METRICS_MONITORED.set(len(self._monitored_metrics))
                CARDINALITY_VIOLATIONS_ACTIVE.set(len(self._violations))

                logger.info(f"Reset cardinality tracking for metric '{metric_name}'")
                return True
            return False


# Global advisor instance
_advisor: CardinalityGuardrailAdvisor | None = None
_advisor_lock = threading.Lock()


def get_cardinality_advisor() -> CardinalityGuardrailAdvisor:
    """Get the global cardinality advisor instance."""
    global _advisor
    if _advisor is None:
        with _advisor_lock:
            if _advisor is None:
                _advisor = CardinalityGuardrailAdvisor()
    return _advisor


def init_cardinality_advisor(
    warning_threshold: int = 100,
    critical_threshold: int = 1000,
    max_sample_labels: int = 10,
    alert_cooldown_seconds: int = 3600,
) -> CardinalityGuardrailAdvisor:
    """Initialize the global cardinality advisor.

    Args:
        warning_threshold: Number of unique labels that triggers warning
        critical_threshold: Number of unique labels that triggers critical alert
        max_sample_labels: Maximum number of sample labels to collect per violation
        alert_cooldown_seconds: Minimum time between alerts for same metric

    Returns:
        The initialized advisor instance
    """
    global _advisor
    with _advisor_lock:
        _advisor = CardinalityGuardrailAdvisor(
            warning_threshold=warning_threshold,
            critical_threshold=critical_threshold,
            max_sample_labels=max_sample_labels,
            alert_cooldown_seconds=alert_cooldown_seconds,
        )
        logger.info("Initialized global cardinality advisor")
        return _advisor


def record_metric_label(metric_name: str, label_value: str) -> None:
    """Record a label value for cardinality monitoring.

    This is a convenience function for easy integration with metrics collection.

    Args:
        metric_name: Name of the metric
        label_value: Value of the label being tracked
    """
    advisor = get_cardinality_advisor()
    advisor.record_label_value(metric_name, label_value)


def get_cardinality_violations() -> list[CardinalityViolation]:
    """Get all current cardinality violations."""
    advisor = get_cardinality_advisor()
    return advisor.get_violations()


def get_advisor_recommendations() -> list[AdvisorRecommendation]:
    """Get advisor recommendations for current violations."""
    advisor = get_cardinality_advisor()
    return advisor.get_recommendations()
