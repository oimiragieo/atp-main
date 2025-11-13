"""GAP-214A: Per-request energy & CO2e attribution.

This module calculates energy consumption and CO2e emissions for model inference,
enabling sustainability metrics and carbon-aware routing decisions.
"""

from typing import Any

from metrics.registry import CO2E_GRAMS_TOTAL, ENERGY_KWH_TOTAL, ENERGY_SAVINGS_PCT

from .carbon_intensity_tracker import get_carbon_tracker


class CarbonEnergyAttribution:
    """Calculates energy consumption and CO2e emissions for model inference."""

    # Joules per token power profiles (based on model size and architecture)
    # Values are approximate and should be calibrated with empirical measurements
    POWER_PROFILES = {
        "large_model": {
            "gpt-4": 0.0025,  # kWh per 1k tokens (high-end GPU inference)
            "claude-3": 0.0023,
            "gemini-1.5": 0.0024,
            "default": 0.0025,
        },
        "specialist_slm": {
            "distilbert": 0.00015,  # kWh per 1k tokens (CPU-efficient)
            "tinyllama": 0.00018,
            "phi-2": 0.00020,
            "default": 0.00017,
        },
        "general_slm": {
            "llama-3-8b": 0.0008,  # kWh per 1k tokens (mid-range GPU)
            "mistral-7b": 0.00075,
            "qwen-7b": 0.00078,
            "default": 0.0008,
        },
    }

    def __init__(self):
        """Initialize the carbon energy attribution calculator."""
        self.carbon_tracker = get_carbon_tracker()

    def calculate_energy_consumption(self, model_name: str, tokens: int, model_category: str) -> float:
        """Calculate energy consumption in kWh for a given model and token count.

        Args:
            model_name: Name of the model
            tokens: Number of tokens processed
            model_category: Category of model ("large_model", "specialist_slm", "general_slm")

        Returns:
            Energy consumption in kWh
        """
        # Get power profile for model category
        category_profiles = self.POWER_PROFILES.get(model_category, {})
        if not category_profiles:
            raise ValueError(f"Unknown model category: {model_category}")

        # Get specific model profile or use default
        kwh_per_1k_tokens = category_profiles.get(model_name, category_profiles.get("default", 0.001))

        # Calculate energy consumption
        energy_kwh = (tokens / 1000.0) * kwh_per_1k_tokens

        # Record energy consumption metric
        ENERGY_KWH_TOTAL.inc(int(energy_kwh * 1000))  # Convert to milli-kWh for integer counter

        return energy_kwh

    def calculate_co2e_emissions(self, energy_kwh: float, region: str) -> float:
        """Calculate CO2e emissions in grams for given energy consumption.

        Args:
            energy_kwh: Energy consumption in kWh
            region: Geographic region for carbon intensity lookup

        Returns:
            CO2e emissions in grams
        """
        # Get carbon intensity in gCO2e/kWh using synchronous method
        intensity = self.get_intensity(region)

        # Convert to grams: kWh * (gCO2e/kWh) * 1000 (since intensity is in kg)
        co2e_grams = energy_kwh * intensity * 1000

        # Record CO2e emissions metric
        CO2E_GRAMS_TOTAL.inc(int(co2e_grams))

        return co2e_grams

    def get_intensity(self, region: str) -> float:
        """Get carbon intensity for a region synchronously.

        Args:
            region: Region code

        Returns:
            Carbon intensity in gCO2e/kWh
        """
        # Check cache first
        data = self.carbon_tracker._cache.get(region)
        if data:
            return data.intensity_gco2_per_kwh

        # Use demo data as fallback
        return self.carbon_tracker._demo_data.get(region, 300.0)

    def compare_energy_savings(
        self, specialist_model: str, large_model: str, tokens: int, region: str
    ) -> dict[str, Any]:
        """Compare energy consumption and CO2e between specialist SLM and large model.

        Args:
            specialist_model: Name of the specialist SLM model
            large_model: Name of the large model
            tokens: Number of tokens processed
            region: Geographic region for carbon intensity

        Returns:
            Dictionary with energy and carbon comparison metrics
        """
        # Calculate energy consumption
        specialist_energy = self.calculate_energy_consumption(specialist_model, tokens, "specialist_slm")
        large_energy = self.calculate_energy_consumption(large_model, tokens, "large_model")

        # Calculate CO2e emissions
        specialist_co2e = self.calculate_co2e_emissions(specialist_energy, region)
        large_co2e = self.calculate_co2e_emissions(large_energy, region)

        # Calculate savings and efficiency
        energy_savings = large_energy - specialist_energy
        carbon_savings = large_co2e - specialist_co2e
        efficiency_ratio = specialist_energy / large_energy if large_energy > 0 else 0.0

        # Calculate energy savings percentage
        energy_savings_pct = (energy_savings / large_energy) * 100.0 if large_energy > 0 else 0.0

        # Record energy savings percentage in histogram
        ENERGY_SAVINGS_PCT.observe(energy_savings_pct)

        return {
            "specialist_energy_kwh": specialist_energy,
            "large_energy_kwh": large_energy,
            "energy_savings_kwh": energy_savings,
            "energy_savings_pct": energy_savings_pct,
            "specialist_co2e_grams": specialist_co2e,
            "large_co2e_grams": large_co2e,
            "carbon_savings_co2e_grams": carbon_savings,
            "efficiency_ratio": efficiency_ratio,
            "region": region,
            "tokens": tokens,
        }


# Global instance for import
carbon_attribution = CarbonEnergyAttribution()
