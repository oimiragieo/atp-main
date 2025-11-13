"""Tests for GAP-367: High-cardinality guardrail advisor."""

import unittest

from router_service.cardinality_guardrail_advisor import (
    AdvisorRecommendation,
    CardinalityGuardrailAdvisor,
    CardinalityViolation,
    get_advisor_recommendations,
    get_cardinality_advisor,
    get_cardinality_violations,
    init_cardinality_advisor,
    record_metric_label,
)


class TestCardinalityGuardrailAdvisor(unittest.TestCase):
    """Test cases for the cardinality guardrail advisor."""

    def setUp(self):
        """Set up test fixtures."""
        self.advisor = CardinalityGuardrailAdvisor(
            warning_threshold=5,
            critical_threshold=10,
            max_sample_labels=3,
            alert_cooldown_seconds=0,  # No cooldown for tests
        )

    def test_initialization(self):
        """Test advisor initialization with custom parameters."""
        advisor = CardinalityGuardrailAdvisor(
            warning_threshold=100,
            critical_threshold=500,
            max_sample_labels=5,
            alert_cooldown_seconds=7200,
        )

        self.assertEqual(advisor.warning_threshold, 100)
        self.assertEqual(advisor.critical_threshold, 500)
        self.assertEqual(advisor.max_sample_labels, 5)
        self.assertEqual(advisor.alert_cooldown_seconds, 7200)

    def test_record_label_value_basic(self):
        """Test basic label value recording."""
        self.advisor.record_label_value("test_metric", "value1")
        self.advisor.record_label_value("test_metric", "value2")
        self.advisor.record_label_value("test_metric", "value1")  # Duplicate

        stats = self.advisor.get_cardinality_stats()
        self.assertEqual(stats["test_metric"]["unique_labels"], 2)
        self.assertFalse(stats["test_metric"]["is_violation"])

    def test_warning_threshold_violation(self):
        """Test warning threshold violation detection."""
        # Add labels up to warning threshold
        for i in range(6):  # Exceeds warning threshold of 5
            self.advisor.record_label_value("test_metric", f"value{i}")

        violations = self.advisor.get_violations()
        self.assertEqual(len(violations), 1)

        violation = violations[0]
        self.assertEqual(violation.metric_name, "test_metric")
        self.assertEqual(violation.unique_labels, 6)
        self.assertEqual(violation.threshold, 5)
        self.assertEqual(len(violation.sample_labels), 3)  # max_sample_labels

    def test_critical_threshold_violation(self):
        """Test critical threshold violation detection."""
        # Add labels up to critical threshold
        for i in range(11):  # Exceeds critical threshold of 10
            self.advisor.record_label_value("test_metric", f"value{i}")

        violations = self.advisor.get_violations()
        self.assertEqual(len(violations), 1)

        violation = violations[0]
        self.assertEqual(violation.metric_name, "test_metric")
        self.assertEqual(violation.unique_labels, 11)
        self.assertEqual(violation.threshold, 10)

    def test_alert_cooldown(self):
        """Test alert cooldown prevents duplicate alerts."""
        advisor = CardinalityGuardrailAdvisor(
            warning_threshold=5,
            critical_threshold=10,
            alert_cooldown_seconds=1,  # 1 second cooldown
        )

        # First violation
        for i in range(6):
            advisor.record_label_value("test_metric", f"value{i}")

        violations1 = advisor.get_violations()
        self.assertEqual(len(violations1), 1)

        # Try to trigger another violation immediately (should be blocked by cooldown)
        for i in range(6, 12):
            advisor.record_label_value("test_metric", f"value{i}")

        violations2 = advisor.get_violations()
        self.assertEqual(len(violations2), 1)  # Should still be 1 due to cooldown

    def test_recommendations_generation(self):
        """Test advisor recommendations generation."""
        # Create a medium severity violation (warning_threshold * 1.5 = 7.5, so 8 labels)
        for i in range(8):
            self.advisor.record_label_value("test_metric", f"value{i}")

        recommendations = self.advisor.get_recommendations()
        self.assertEqual(len(recommendations), 1)

        rec = recommendations[0]
        self.assertEqual(rec.metric_name, "test_metric")
        self.assertEqual(rec.severity, "medium")
        self.assertIn("Consider aggregating", rec.action)
        self.assertIn("approaching critical levels", rec.rationale)

    def test_critical_recommendations(self):
        """Test critical severity recommendations."""
        # Create a critical violation
        for i in range(12):
            self.advisor.record_label_value("test_metric", f"value{i}")

        recommendations = self.advisor.get_recommendations()
        self.assertEqual(len(recommendations), 1)

        rec = recommendations[0]
        self.assertEqual(rec.severity, "high")
        self.assertIn("Review and optimize", rec.action)

    def test_extreme_cardinality_recommendations(self):
        """Test extreme cardinality recommendations."""
        # Create extreme violation (2x critical threshold)
        for i in range(21):
            self.advisor.record_label_value("test_metric", f"value{i}")

        recommendations = self.advisor.get_recommendations()
        self.assertEqual(len(recommendations), 1)

        rec = recommendations[0]
        self.assertEqual(rec.severity, "critical")
        self.assertIn("Immediate action required", rec.action)

    def test_label_optimization_suggestions(self):
        """Test label optimization suggestions."""
        # Use advisor with higher max_sample_labels for this test
        advisor = CardinalityGuardrailAdvisor(
            warning_threshold=5,
            critical_threshold=10,
            max_sample_labels=10,  # Higher to capture more patterns
            alert_cooldown_seconds=0,
        )

        # Create labels with patterns that can be optimized
        labels = [
            "user_12345",
            "user_12346",
            "user_12347",  # Numeric pattern
            "very_long_label_name_that_exceeds_normal_length_and_should_be_truncated",
            "short",
            "medium_length",
            "another_very_long_label_name_here",  # Length variation
            "api_v1_endpoint",
            "api_v2_endpoint",
            "db_v1_query",  # Multiple prefixes
        ]

        for label in labels:
            advisor.record_label_value("test_metric", label)

        recommendations = advisor.get_recommendations()
        self.assertEqual(len(recommendations), 1)

        rec = recommendations[0]
        self.assertIsNotNone(rec.suggested_labels)
        suggestions = rec.suggested_labels

        # Should detect numeric pattern
        numeric_suggestion = any("aggregating numeric" in s for s in suggestions)
        self.assertTrue(numeric_suggestion, "Should suggest aggregating numeric IDs")

        # Should detect long labels
        long_label_suggestion = any("truncating or hashing" in s for s in suggestions)
        self.assertTrue(long_label_suggestion, "Should suggest truncating long labels")

        # Should detect multiple prefixes
        prefix_suggestion = any("prefixes detected" in s for s in suggestions)
        self.assertTrue(prefix_suggestion, "Should suggest consistent naming for prefixes")

    def test_clear_violation(self):
        """Test clearing violations."""
        # Create violation
        for i in range(6):
            self.advisor.record_label_value("test_metric", f"value{i}")

        self.assertEqual(len(self.advisor.get_violations()), 1)

        # Clear violation
        result = self.advisor.clear_violation("test_metric")
        self.assertTrue(result)
        self.assertEqual(len(self.advisor.get_violations()), 0)

        # Try to clear non-existent violation
        result = self.advisor.clear_violation("non_existent")
        self.assertFalse(result)

    def test_reset_metric(self):
        """Test resetting metric cardinality tracking."""
        # Add some data
        for i in range(6):
            self.advisor.record_label_value("test_metric", f"value{i}")

        self.assertIn("test_metric", self.advisor.get_cardinality_stats())

        # Reset metric
        result = self.advisor.reset_metric("test_metric")
        self.assertTrue(result)
        self.assertNotIn("test_metric", self.advisor.get_cardinality_stats())

        # Try to reset non-existent metric
        result = self.advisor.reset_metric("non_existent")
        self.assertFalse(result)

    def test_multiple_metrics(self):
        """Test monitoring multiple metrics simultaneously."""
        # Metric 1: Normal
        for i in range(3):
            self.advisor.record_label_value("metric1", f"value{i}")

        # Metric 2: Warning violation
        for i in range(6):
            self.advisor.record_label_value("metric2", f"value{i}")

        # Metric 3: Critical violation
        for i in range(11):
            self.advisor.record_label_value("metric3", f"value{i}")

        stats = self.advisor.get_cardinality_stats()
        self.assertEqual(len(stats), 3)

        violations = self.advisor.get_violations()
        self.assertEqual(len(violations), 2)  # metric2 and metric3

        recommendations = self.advisor.get_recommendations()
        self.assertEqual(len(recommendations), 2)

    def test_get_cardinality_stats(self):
        """Test cardinality statistics retrieval."""
        # Add data to multiple metrics
        for i in range(3):
            self.advisor.record_label_value("metric1", f"value{i}")

        for i in range(7):  # Warning violation
            self.advisor.record_label_value("metric2", f"value{i}")

        stats = self.advisor.get_cardinality_stats()

        self.assertEqual(stats["metric1"]["unique_labels"], 3)
        self.assertFalse(stats["metric1"]["is_violation"])

        self.assertEqual(stats["metric2"]["unique_labels"], 7)
        self.assertTrue(stats["metric2"]["is_violation"])


class TestGlobalFunctions(unittest.TestCase):
    """Test global functions for cardinality advisor."""

    def setUp(self):
        """Reset global advisor before each test."""
        # Reset the global advisor
        import router_service.cardinality_guardrail_advisor as cga

        cga._advisor = None

    def test_get_cardinality_advisor(self):
        """Test getting global advisor instance."""
        advisor1 = get_cardinality_advisor()
        advisor2 = get_cardinality_advisor()

        self.assertIs(advisor1, advisor2)  # Should be same instance

    def test_init_cardinality_advisor(self):
        """Test initializing global advisor."""
        advisor = init_cardinality_advisor(
            warning_threshold=50,
            critical_threshold=200,
        )

        self.assertEqual(advisor.warning_threshold, 50)
        self.assertEqual(advisor.critical_threshold, 200)

        # Should return same instance
        advisor2 = get_cardinality_advisor()
        self.assertIs(advisor, advisor2)

    def test_record_metric_label(self):
        """Test global record_metric_label function."""
        record_metric_label("test_metric", "value1")
        record_metric_label("test_metric", "value2")

        violations = get_cardinality_violations()
        self.assertEqual(len(violations), 0)  # No violation yet

        stats = get_cardinality_advisor().get_cardinality_stats()
        self.assertEqual(stats["test_metric"]["unique_labels"], 2)

    def test_get_cardinality_violations(self):
        """Test global get_cardinality_violations function."""
        # Initialize advisor with test-friendly parameters
        from router_service.cardinality_guardrail_advisor import init_cardinality_advisor

        init_cardinality_advisor(warning_threshold=5, critical_threshold=10)

        # Create violation
        for i in range(6):
            record_metric_label("test_metric", f"value{i}")

        violations = get_cardinality_violations()
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].metric_name, "test_metric")

    def test_get_advisor_recommendations(self):
        """Test global get_advisor_recommendations function."""
        # Initialize advisor with test-friendly parameters
        from router_service.cardinality_guardrail_advisor import init_cardinality_advisor

        init_cardinality_advisor(warning_threshold=5, critical_threshold=10)

        # Create violation
        for i in range(6):
            record_metric_label("test_metric", f"value{i}")

        recommendations = get_advisor_recommendations()
        self.assertEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0].metric_name, "test_metric")


class TestAdvisorRecommendation(unittest.TestCase):
    """Test AdvisorRecommendation dataclass."""

    def test_recommendation_creation(self):
        """Test creating advisor recommendations."""
        rec = AdvisorRecommendation(
            metric_name="test_metric",
            severity="high",
            action="Review label usage",
            rationale="High cardinality detected",
            estimated_impact="Performance degradation",
            suggested_labels=["Aggregate user IDs", "Use ranges"],
        )

        self.assertEqual(rec.metric_name, "test_metric")
        self.assertEqual(rec.severity, "high")
        self.assertEqual(rec.action, "Review label usage")
        self.assertEqual(rec.rationale, "High cardinality detected")
        self.assertEqual(rec.estimated_impact, "Performance degradation")
        self.assertEqual(rec.suggested_labels, ["Aggregate user IDs", "Use ranges"])


class TestCardinalityViolation(unittest.TestCase):
    """Test CardinalityViolation dataclass."""

    def test_violation_creation(self):
        """Test creating cardinality violations."""
        violation = CardinalityViolation(
            metric_name="test_metric",
            unique_labels=150,
            threshold=100,
            timestamp=1234567890.0,
            sample_labels=["value1", "value2", "value3"],
        )

        self.assertEqual(violation.metric_name, "test_metric")
        self.assertEqual(violation.unique_labels, 150)
        self.assertEqual(violation.threshold, 100)
        self.assertEqual(violation.timestamp, 1234567890.0)
        self.assertEqual(violation.sample_labels, ["value1", "value2", "value3"])


if __name__ == "__main__":
    unittest.main()
