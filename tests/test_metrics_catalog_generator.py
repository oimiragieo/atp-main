"""Tests for GAP-210: Central metrics catalog generator."""

import os
import tempfile
import unittest
from unittest.mock import patch

from tools.metrics_catalog_generator import MetricsCatalogGenerator


class TestMetricsCatalogGenerator(unittest.TestCase):
    """Test cases for metrics catalog generator."""

    def setUp(self):
        """Set up test fixtures."""
        self.generator = MetricsCatalogGenerator()

    def test_generate_catalog_structure(self):
        """Test that generated catalog has correct structure."""
        catalog = self.generator.generate_catalog()

        # Check required fields
        self.assertIn("metrics", catalog)
        self.assertIn("version", catalog)
        self.assertIn("generated_at", catalog)
        self.assertIn("total_metrics", catalog)

        # Check metrics is a list
        self.assertIsInstance(catalog["metrics"], list)

        # Check we have some metrics
        self.assertGreater(len(catalog["metrics"]), 0)

    def test_known_metrics_included(self):
        """Test that all known metrics are included in catalog."""
        catalog = self.generator.generate_catalog()
        metric_names = {m["name"] for m in catalog["metrics"]}

        # Check some key known metrics are present
        expected_metrics = [
            "atp_router_requests_total",
            "atp_router_request_duration_seconds",
            "slm_energy_savings_kwh_total",
            "slm_carbon_savings_co2e_grams_total",
        ]

        for metric in expected_metrics:
            self.assertIn(metric, metric_names, f"Expected metric {metric} not found")

    def test_metric_structure(self):
        """Test that each metric has required fields."""
        catalog = self.generator.generate_catalog()

        for metric in catalog["metrics"]:
            self.assertIn("name", metric)
            self.assertIn("type", metric)
            self.assertIn("description", metric)
            self.assertIn("unit", metric)
            self.assertIn("buckets", metric)
            self.assertIn("labels", metric)

            # Check type is valid
            self.assertIn(metric["type"], ["counter", "histogram", "gauge"])

            # Check buckets is list
            self.assertIsInstance(metric["buckets"], list)

            # Check labels is list
            self.assertIsInstance(metric["labels"], list)

    def test_catalog_validation_valid(self):
        """Test validation of a valid catalog."""
        catalog = self.generator.generate_catalog()
        errors = self.generator.validate_catalog(catalog)

        self.assertEqual(len(errors), 0, f"Valid catalog should have no errors, got: {errors}")

    def test_catalog_validation_missing_metrics(self):
        """Test validation of catalog missing metrics field."""
        invalid_catalog = {"version": "1.0.0"}
        errors = self.generator.validate_catalog(invalid_catalog)

        self.assertIn("Missing 'metrics' field", errors)

    def test_catalog_validation_invalid_metrics_type(self):
        """Test validation of catalog with invalid metrics type."""
        invalid_catalog = {"metrics": "not_a_list"}
        errors = self.generator.validate_catalog(invalid_catalog)

        self.assertIn("'metrics' field must be a list", errors)

    def test_catalog_validation_missing_required_fields(self):
        """Test validation of metric missing required fields."""
        invalid_catalog = {
            "metrics": [
                {"name": "test_metric"},  # Missing type and description
                {"type": "counter"},  # Missing name and description
            ]
        }
        errors = self.generator.validate_catalog(invalid_catalog)

        self.assertGreater(len(errors), 0)
        self.assertIn("missing required field 'type'", " ".join(errors))
        self.assertIn("missing required field 'description'", " ".join(errors))

    def test_catalog_validation_invalid_type(self):
        """Test validation of metric with invalid type."""
        invalid_catalog = {"metrics": [{"name": "test_metric", "type": "invalid_type", "description": "Test metric"}]}
        errors = self.generator.validate_catalog(invalid_catalog)

        self.assertIn("has invalid type 'invalid_type'", " ".join(errors))

    def test_save_and_load_catalog(self):
        """Test saving and loading catalog."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            # Generate and save catalog
            self.generator.save_catalog(temp_path)

            # Load and validate
            loaded_catalog, errors = self.generator.load_and_validate_catalog(temp_path)

            self.assertEqual(len(errors), 0, f"Loaded catalog should be valid: {errors}")
            self.assertIn("metrics", loaded_catalog)
            self.assertIn("version", loaded_catalog)

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_load_invalid_json(self):
        """Test loading invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json content")
            temp_path = f.name

        try:
            catalog, errors = self.generator.load_and_validate_catalog(temp_path)

            self.assertEqual(catalog, {})
            self.assertGreater(len(errors), 0)
            self.assertIn("Failed to load catalog", errors[0])

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_load_nonexistent_file(self):
        """Test loading nonexistent file."""
        catalog, errors = self.generator.load_and_validate_catalog("/nonexistent/file.json")

        self.assertEqual(catalog, {})
        self.assertGreater(len(errors), 0)
        self.assertIn("Failed to load catalog", errors[0])

    @patch("tools.metrics_catalog_generator.REGISTRY")
    def test_registry_integration(self, mock_registry):
        """Test integration with metrics registry."""
        # Mock registry export
        mock_registry.export.return_value = {
            "counters": {"custom_counter": {"value": 42}},
            "gauges": {"custom_gauge": {"value": 3.14}},
            "histograms": {"custom_histogram": {"count": 10}},
        }

        catalog = self.generator.generate_catalog()
        metric_names = {m["name"] for m in catalog["metrics"]}

        # Check that custom metrics from registry are included
        self.assertIn("custom_counter", metric_names)
        self.assertIn("custom_gauge", metric_names)
        self.assertIn("custom_histogram", metric_names)

    def test_metrics_sorting(self):
        """Test that metrics are sorted by name."""
        catalog = self.generator.generate_catalog()
        metric_names = [m["name"] for m in catalog["metrics"]]

        self.assertEqual(metric_names, sorted(metric_names))

    def test_catalog_schema_compliance(self):
        """Test that catalog complies with defined schema."""
        catalog = self.generator.generate_catalog()

        # Check schema field
        self.assertEqual(catalog.get("$schema"), "http://json-schema.org/draft-07/schema#")

        # This is a basic check - in a real scenario, we'd use a JSON schema validator
        # For now, we check that the structure matches our expectations
        self.assertIsInstance(catalog["metrics"], list)
        self.assertIsInstance(catalog["version"], str)
        self.assertIsInstance(catalog["generated_at"], str)


if __name__ == "__main__":
    unittest.main()
