"""Example of integrating the real-time pricing monitoring system."""

import asyncio
import logging

from .cost_aggregator import ENHANCED_COST
from .pricing import PricingConfig, PricingManager, initialize_pricing_manager

logger = logging.getLogger(__name__)


async def demonstrate_basic_pricing_operations():
    """Demonstrate basic pricing operations."""
    print("=== Basic Pricing Operations ===\n")

    # Initialize pricing manager
    config = PricingConfig(
        enabled=True,
        update_interval_seconds=60,  # 1 minute for demo
        change_detection_enabled=True,
        validation_enabled=True,
        alerts_enabled=False,  # Disable alerts for demo
    )

    pricing_manager = await initialize_pricing_manager(config)

    print("1. Getting current pricing for models...")

    # Get pricing for specific models
    models_to_check = [
        ("openai", "gpt-4"),
        ("openai", "gpt-3.5-turbo"),
        ("anthropic", "claude-3-opus-20240229"),
        ("google", "gemini-pro"),
    ]

    for provider, model in models_to_check:
        pricing = await pricing_manager.get_model_pricing(provider, model)
        if pricing:
            print(f"   {provider}:{model}")
            print(f"     Input: ${pricing['input']:.6f} per 1K tokens")
            print(f"     Output: ${pricing['output']:.6f} per 1K tokens")
        else:
            print(f"   {provider}:{model} - No pricing data available")

    print("\n2. Calculating request costs...")

    # Calculate costs for sample requests
    sample_requests = [
        {"provider": "openai", "model": "gpt-4", "input_tokens": 1000, "output_tokens": 500},
        {"provider": "openai", "model": "gpt-3.5-turbo", "input_tokens": 2000, "output_tokens": 800},
        {"provider": "anthropic", "model": "claude-3-opus-20240229", "input_tokens": 1500, "output_tokens": 600},
    ]

    for request in sample_requests:
        cost_result = await pricing_manager.calculate_request_cost(**request)

        if "error" not in cost_result:
            print(f"   {request['provider']}:{request['model']}")
            print(f"     Tokens: {request['input_tokens']} in, {request['output_tokens']} out")
            print(f"     Cost: ${cost_result['total_cost_usd']:.6f}")
            print(f"     Breakdown: ${cost_result['input_cost_usd']:.6f} + ${cost_result['output_cost_usd']:.6f}")
        else:
            print(f"   {request['provider']}:{request['model']} - Error: {cost_result['error']}")

    await pricing_manager.stop()
    print()


async def demonstrate_cost_tracking_integration():
    """Demonstrate integration with enhanced cost tracking."""
    print("=== Enhanced Cost Tracking Integration ===\n")

    print("1. Recording requests with enhanced cost tracking...")

    # Simulate some requests
    sample_requests = [
        {
            "provider": "openai",
            "model": "gpt-4",
            "input_tokens": 1200,
            "output_tokens": 400,
            "tenant_id": "tenant-123",
            "qos": "gold",
        },
        {
            "provider": "openai",
            "model": "gpt-3.5-turbo",
            "input_tokens": 800,
            "output_tokens": 300,
            "tenant_id": "tenant-456",
            "qos": "silver",
        },
        {
            "provider": "anthropic",
            "model": "claude-3-opus-20240229",
            "input_tokens": 1000,
            "output_tokens": 500,
            "tenant_id": "tenant-123",
            "qos": "gold",
        },
    ]

    for request in sample_requests:
        result = await ENHANCED_COST.record_request_cost(**request)

        if "error" not in result:
            print(f"   ✅ {request['provider']}:{request['model']}")
            print(f"      Cost: ${result['final_cost_usd']:.6f}")
            print(f"      Tenant: {request['tenant_id']}")
        else:
            print(f"   ❌ {request['provider']}:{request['model']} - Error: {result['error']}")

    print("\n2. Enhanced cost snapshot...")
    snapshot = ENHANCED_COST.enhanced_snapshot()

    print("   Provider costs:")
    for provider, cost in snapshot["provider_costs"].items():
        print(f"     {provider}: ${cost:.6f}")

    print("   Model costs:")
    for model, cost in list(snapshot["model_costs"].items())[:5]:  # Top 5
        print(f"     {model}: ${cost:.6f}")

    print("   Tenant costs:")
    for tenant, cost in snapshot["tenant_costs"].items():
        print(f"     {tenant}: ${cost:.6f}")

    print("   Token usage by provider:")
    for provider, tokens in snapshot["token_usage"]["by_provider"].items():
        total_tokens = tokens["input"] + tokens["output"]
        print(f"     {provider}: {total_tokens:,} tokens ({tokens['input']:,} in, {tokens['output']:,} out)")

    print()


async def demonstrate_pricing_validation():
    """Demonstrate pricing validation against actual costs."""
    print("=== Pricing Validation ===\n")

    config = PricingConfig(
        enabled=False,  # Don't start monitoring for this demo
        validation_enabled=True,
        validation_tolerance_percent=10.0,
    )

    pricing_manager = PricingManager(config)

    print("1. Validating actual costs against expected pricing...")

    # Simulate validation scenarios
    validation_scenarios = [
        {
            "provider": "openai",
            "model": "gpt-4",
            "input_tokens": 1000,
            "output_tokens": 500,
            "actual_cost": 0.045,  # Close to expected
            "scenario": "Within tolerance",
        },
        {
            "provider": "openai",
            "model": "gpt-3.5-turbo",
            "input_tokens": 2000,
            "output_tokens": 800,
            "actual_cost": 0.010,  # Significantly different
            "scenario": "Outside tolerance",
        },
    ]

    for scenario in validation_scenarios:
        print(f"   Scenario: {scenario['scenario']}")

        validation_result = await pricing_manager.validate_actual_cost(
            provider=scenario["provider"],
            model=scenario["model"],
            input_tokens=scenario["input_tokens"],
            output_tokens=scenario["output_tokens"],
            actual_cost=scenario["actual_cost"],
        )

        if "error" not in validation_result:
            expected_cost = validation_result["expected_breakdown"]["total_cost_usd"]
            variance = validation_result.get("variance_percent", 0)
            within_tolerance = validation_result.get("within_tolerance", False)

            print(f"     Model: {scenario['provider']}:{scenario['model']}")
            print(f"     Expected: ${expected_cost:.6f}")
            print(f"     Actual: ${scenario['actual_cost']:.6f}")
            print(f"     Variance: {variance:.1f}%")
            print(f"     Within tolerance: {'✅' if within_tolerance else '❌'}")
        else:
            print(f"     Error: {validation_result['error']}")

        print()


async def demonstrate_cost_optimization():
    """Demonstrate cost optimization recommendations."""
    print("=== Cost Optimization Recommendations ===\n")

    pricing_manager = PricingManager(PricingConfig(enabled=False))

    print("1. Generating cost optimization recommendations...")

    # Simulate current usage patterns
    current_usage = {
        "openai": {
            "gpt-4": 50000,  # 50K tokens
            "gpt-3.5-turbo": 100000,  # 100K tokens
        },
        "anthropic": {
            "claude-3-opus-20240229": 25000  # 25K tokens
        },
    }

    recommendations = await pricing_manager.get_cost_optimization_recommendations(current_usage)

    if recommendations:
        print("   💡 Optimization opportunities found:")

        for rec in recommendations[:3]:  # Show top 3
            current = rec["current"]
            best_alt = rec["alternatives"][0] if rec["alternatives"] else None

            print(f"\n   Current: {current['provider']}:{current['model']}")
            print(f"     Usage: {current['token_count']:,} tokens")
            print(f"     Cost: ${current['cost_usd']:.6f}")

            if best_alt:
                print(f"   💰 Best alternative: {best_alt['provider']}:{best_alt['model']}")
                print(f"     Cost: ${best_alt['cost_usd']:.6f}")
                print(f"     Savings: ${best_alt['savings_usd']:.6f} ({best_alt['savings_percent']:.1f}%)")
    else:
        print("   ℹ️  No optimization opportunities found with current pricing data")

    print()


async def demonstrate_pricing_trends():
    """Demonstrate pricing trends and change detection."""
    print("=== Pricing Trends and Change Detection ===\n")

    pricing_manager = PricingManager(PricingConfig(enabled=False))

    print("1. Checking for recent pricing changes...")

    # Get pricing trends
    trends = await pricing_manager.get_pricing_trends(hours=24)

    print(f"   📊 Pricing changes in last 24 hours: {trends['total_changes']}")
    print(f"   🚨 Significant changes: {trends['significant_changes']}")
    print(f"   ⚠️  Moderate changes: {trends['moderate_changes']}")

    if trends["significant_changes_detail"]:
        print("\n   Significant changes detected:")
        for change in trends["significant_changes_detail"][:3]:  # Show first 3
            provider = change.get("provider", "unknown")
            model = change.get("model", "unknown")
            change_percent = change.get("change_percent", 0)
            pricing_type = change.get("type", "unknown")

            direction = "📈" if change_percent > 0 else "📉"
            print(f"     {direction} {provider}:{model} ({pricing_type})")
            print(f"       Change: {abs(change_percent):.1f}%")
    else:
        print("   ✅ No significant pricing changes detected")

    print()


async def demonstrate_system_health_monitoring():
    """Demonstrate system health monitoring."""
    print("=== System Health Monitoring ===\n")

    pricing_manager = PricingManager(PricingConfig(enabled=False))

    print("1. Checking pricing system health...")

    health = await pricing_manager.get_system_health()

    print(f"   Overall status: {'✅ Healthy' if health['pricing_monitoring'] else '❌ Unhealthy'}")

    # Component health
    if "components" in health:
        print("   Component status:")
        for component, status in health["components"].items():
            if isinstance(status, dict):
                component_status = status.get("status", "unknown")
                print(f"     {component}: {'✅' if component_status == 'healthy' else '❌'} {component_status}")
            else:
                print(f"     {component}: {status}")

    # Cache health
    if "cache" in health:
        cache_info = health["cache"]
        print(f"   Cache: {cache_info.get('total_models', 0)} models cached")
        print(f"   Stale entries: {cache_info.get('stale_entries', 0)}")

    # Staleness info
    if "staleness" in health:
        staleness = health["staleness"]
        print(f"   Stale pricing entries: {staleness['stale_count']}")
        print(f"   Staleness threshold: {staleness['threshold_seconds']}s")

    print("\n2. Getting cost optimization insights...")

    insights = await ENHANCED_COST.get_cost_optimization_insights()

    if "error" not in insights:
        print("   💰 Top cost providers:")
        for provider_info in insights["top_cost_providers"][:3]:
            print(f"     {provider_info['provider']}: ${provider_info['cost_usd']:.6f}")

        print("   🤖 Top cost models:")
        for model_info in insights["top_cost_models"][:3]:
            print(f"     {model_info['model']}: ${model_info['cost_usd']:.6f}")

        if insights["recommendations"]:
            total_savings = sum(rec["max_savings_usd"] for rec in insights["recommendations"])
            print(f"   💡 Potential savings: ${total_savings:.6f}")
    else:
        print(f"   ❌ Error getting insights: {insights['error']}")

    print()


async def main():
    """Main demonstration function."""
    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Suppress verbose logs
    logging.getLogger("router_service.pricing").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

    try:
        print("🚀 Real-time Pricing Monitoring System Demonstration\n")

        # Run demonstrations
        await demonstrate_basic_pricing_operations()
        await demonstrate_cost_tracking_integration()
        await demonstrate_pricing_validation()
        await demonstrate_cost_optimization()
        await demonstrate_pricing_trends()
        await demonstrate_system_health_monitoring()

        print("✅ All demonstrations completed successfully!")

    except Exception as e:
        print(f"❌ Demonstration failed: {e}")
        logger.exception("Demonstration execution failed")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
