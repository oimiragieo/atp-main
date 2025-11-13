# Sustainability Metrics Guide

## Overview

GAP-214A introduces comprehensive energy and CO2e attribution for ATP Router routing decisions, enabling carbon-aware routing and detailed sustainability tracking. This guide covers the sustainability metrics implementation, usage, and interpretation.

## Energy Attribution Architecture

### Core Components

1. **CarbonEnergyAttribution Class** (`router_service/carbon_energy_attribution.py`)
   - Calculates energy consumption per model inference
   - Computes CO2e emissions using regional carbon intensity data
   - Provides comparative analysis between model types

2. **Power Profiles** (Joules per token)
   - **Large Models**: ~2.5 kWh per 1k tokens (GPT-4, Claude-3, Gemini-1.5)
   - **General SLMs**: ~0.8 kWh per 1k tokens (Llama-3-8B, Mistral-7B)
   - **Specialist SLMs**: ~0.17 kWh per 1k tokens (DistilBERT, TinyLlama)

3. **Regional Carbon Intensity** (gCO2e/kWh)
   - **Low Carbon**: EU-West (150), EU-Central (180)
   - **Medium Carbon**: US-West (200), US-East (250)
   - **High Carbon**: Asia-East (400)

## Metrics Implementation

### Energy Consumption Metrics

#### `energy_kwh_total` (Counter)
- **Description**: Total energy consumption in kilowatt-hours across all routing decisions
- **Unit**: kWh (stored as milli-kWh internally for precision)
- **Labels**: None (global aggregate)
- **Usage**: Track cumulative energy usage for sustainability reporting

```python
# Example: Record 0.0025 kWh energy consumption
ENERGY_KWH_TOTAL.inc(2.5)  # 2.5 milli-kWh = 0.0025 kWh
```

#### `co2e_grams_total` (Counter)
- **Description**: Total CO2e emissions in grams across all routing decisions
- **Unit**: grams CO2e
- **Labels**: None (global aggregate)
- **Usage**: Track carbon footprint for environmental impact assessment

```python
# Example: Record 500 grams CO2e emissions
CO2E_GRAMS_TOTAL.inc(500)
```

#### `energy_savings_pct` (Histogram)
- **Description**: Distribution of energy savings percentages when using SLMs vs large models
- **Unit**: Percentage (0-100%)
- **Buckets**: [0.0, 10.0, 25.0, 50.0, 75.0, 90.0, 100.0]
- **Usage**: Analyze the effectiveness of SLM routing decisions

```python
# Example: Record 85% energy savings
ENERGY_SAVINGS_PCT.observe(85.0)
```

## Per-Request Attribution

### Energy Attribution Data Structure

Each routing decision includes detailed energy attribution:

```python
{
    "model_name": "distilbert",
    "model_category": "specialist_slm",
    "energy_kwh": 0.00015,        # Energy consumption for this request
    "co2e_grams": 22.5,           # CO2e emissions for this request
    "region": "us-west",          # Geographic region
    "total_tokens": 1000          # Token count processed
}
```

### Comparative Analysis

The `compare_energy_savings()` method provides comparative metrics:

```python
result = energy_calculator.compare_energy_savings(
    "distilbert", "gpt-4", 1000, "us-west"
)

# Returns:
{
    "specialist_energy_kwh": 0.00015,
    "large_energy_kwh": 0.0025,
    "energy_savings_kwh": 0.00235,
    "energy_savings_pct": 94.0,
    "specialist_co2e_grams": 22.5,
    "large_co2e_grams": 375.0,
    "carbon_savings_co2e_grams": 352.5,
    "efficiency_ratio": 0.06,
    "region": "us-west",
    "tokens": 1000
}
```

## Integration with Routing

### Router Service Integration

The `choose_model.py` integrates energy attribution into routing decisions:

```python
plan, regret_analysis, energy_attribution = choose(
    quality="balanced",
    latency_slo_ms=1200,
    registry=registry,
    total_tokens=1000
)

# Energy attribution is automatically calculated and metrics recorded
print(f"Energy used: {energy_attribution['energy_kwh']} kWh")
print(f"CO2e emitted: {energy_attribution['co2e_grams']} grams")
```

### Carbon-Aware Routing

Energy attribution enables carbon-aware routing decisions:

1. **Regional Optimization**: Route to lower-carbon regions when latency allows
2. **Model Selection**: Prefer energy-efficient models for cost and environmental benefit
3. **Load Balancing**: Distribute load based on regional carbon intensity

## Monitoring and Dashboards

### Key Performance Indicators

1. **Energy Efficiency Ratio**: SLM energy use vs large model baseline
2. **Carbon Savings**: Total CO2e avoided through efficient routing
3. **Regional Distribution**: Energy consumption by geographic region
4. **Model Efficiency**: Energy per token by model type

### Sample Queries

```prometheus
# Total energy consumption
sum(rate(energy_kwh_total[5m])) by (instance)

# CO2e emissions by region
sum(rate(co2e_grams_total[5m])) by (region)

# Energy savings distribution
histogram_quantile(0.95, sum(rate(energy_savings_pct_bucket[5m])) by (le))
```

## Calibration and Tuning

### Power Profile Calibration

Power profiles should be calibrated with empirical measurements:

1. **Hardware Monitoring**: GPU/CPU power consumption during inference
2. **Token Counting**: Accurate input/output token measurement
3. **Regional Data**: Real carbon intensity data from electricity providers
4. **Model Updates**: Profile updates when new model versions are deployed

### Accuracy Considerations

- Power profiles are approximate and should be treated as estimates
- Regional carbon intensity data may vary by time and provider
- Actual energy consumption depends on hardware, utilization, and cooling
- Metrics provide relative comparisons rather than absolute measurements

## Future Enhancements

### Planned Improvements

1. **Dynamic Power Profiling**: Real-time power consumption measurement
2. **Hardware-Specific Profiles**: Different profiles for CPU vs GPU inference
3. **Time-of-Use Pricing**: Energy cost optimization based on electricity pricing
4. **Carbon Credit Integration**: Automatic carbon credit calculation and tracking
5. **Sustainability Reporting**: Automated reports for environmental compliance

### Integration Points

- **Carbon Intensity API**: Real-time carbon intensity data feeds
- **Energy Monitoring**: Hardware-level power consumption sensors
- **Cost Optimization**: Integration with energy pricing APIs
- **Regulatory Reporting**: Automated sustainability disclosures

## Troubleshooting

### Common Issues

1. **Missing Metrics**: Ensure `CarbonEnergyAttribution` is properly initialized
2. **Zero Values**: Check that token counts are correctly passed to calculations
3. **Incorrect Regions**: Verify region codes match carbon intensity data
4. **Performance Impact**: Energy calculations are lightweight but monitor for overhead

### Validation

```python
# Test energy calculation
energy = calculator.calculate_energy_consumption("gpt-4", 1000, "large_model")
assert abs(energy - 0.0025) < 1e-6  # Should be ~0.0025 kWh

# Test CO2e calculation
co2e = calculator.calculate_co2e_emissions(0.0025, "us-west")
expected = 0.0025 * 200 * 1000  # 500 grams
assert abs(co2e - expected) < 1e-6
```

## References

- **GAP-213**: Carbon intensity tracking implementation
- **GAP-214**: Request-level cost/regret savings KPI
- **Power Profiles**: Based on MLPerf and academic energy consumption studies
- **Carbon Intensity**: Regional grid emission factors from electricity providers</content>
<parameter name="filePath">c:\dev\projects\atp-main\docs\35_Sustainability_Metrics_Guide.md
