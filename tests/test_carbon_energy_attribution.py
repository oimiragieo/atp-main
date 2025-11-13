"""Tests for GAP-349: Carbon & energy savings attribution."""


from router_service.carbon_energy_attribution import CarbonEnergyAttribution


class TestCarbonEnergyAttribution:
    """Test carbon and energy attribution functionality."""

    def setup_method(self):
        """Set up test instance."""
        self.attribution = CarbonEnergyAttribution()

    def test_calculate_energy_consumption_large_model(self):
        """Test energy calculation for large models."""
        # Test GPT-4 energy consumption
        energy = self.attribution.calculate_energy_consumption("gpt-4", 1000, "large_model")
        expected = (1000 / 1000.0) * 0.0025  # 2.5 kWh per 1k tokens
        assert abs(energy - expected) < 1e-10

    def test_calculate_energy_consumption_slm(self):
        """Test energy calculation for SLM specialists."""
        # Test DistilBERT energy consumption
        energy = self.attribution.calculate_energy_consumption("distilbert", 1000, "specialist_slm")
        expected = (1000 / 1000.0) * 0.00015  # 0.15 kWh per 1k tokens
        assert abs(energy - expected) < 1e-10

    def test_compare_energy_savings(self):
        """Test energy savings comparison between models."""
        result = self.attribution.compare_energy_savings("distilbert", "gpt-4", 1000, "us-west")

        # Check that all expected keys are present
        expected_keys = [
            "specialist_energy_kwh",
            "large_energy_kwh",
            "energy_savings_kwh",
            "specialist_co2e_grams",
            "large_co2e_grams",
            "carbon_savings_co2e_grams",
            "efficiency_ratio",
            "region",
        ]
        for key in expected_keys:
            assert key in result

        # Check that SLM uses less energy than large model
        assert result["specialist_energy_kwh"] < result["large_energy_kwh"]
        assert result["energy_savings_kwh"] > 0
        assert result["carbon_savings_co2e_grams"] > 0
        assert result["efficiency_ratio"] < 1.0  # SLM should be more efficient
