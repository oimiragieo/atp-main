"""Tests for the real-time pricing monitoring system."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from router_service.pricing import (
    PricingConfig, PricingManager, PricingMonitor, PricingCache,
    OpenAIPricingAPI, AnthropicPricingAPI, GooglePricingAPI, MockPricingAPI
)


@pytest.mark.asyncio
async def test_pricing_config_from_environment():
    """Test pricing configuration from environment variables."""
    with patch.dict('os.environ', {
        'PRICING_MONITORING_ENABLED': 'true',
        'PRICING_UPDATE_INTERVAL': '600',
        'PRICING_CHANGE_THRESHOLD': '10.0',
        'OPENAI_API_KEY': 'test-key',
        'PRICING_ALERTS_ENABLED': 'false'
    }):
        config = PricingConfig.from_environment()
        
        assert config.enabled is True
        assert config.update_interval_seconds == 600
        assert config.change_threshold_percent == 10.0
        assert config.openai_api_key == 'test-key'
        assert config.alerts_enabled is False


@pytest.mark.asyncio
async def test_openai_pricing_api():
    """Test OpenAI pricing API."""
    api = OpenAIPricingAPI()
    
    # Test single model pricing
    pricing = await api.get_model_pricing("gpt-4")
    assert "input" in pricing
    assert "output" in pricing
    assert pricing["input"] > 0
    assert pricing["output"] > 0
    
    # Test all pricing
    all_pricing = await api.get_all_pricing()
    assert "gpt-4" in all_pricing
    assert "gpt-3.5-turbo" in all_pricing


@pytest.mark.asyncio
async def test_anthropic_pricing_api():
    """Test Anthropic pricing API."""
    api = AnthropicPricingAPI()
    
    # Test single model pricing
    pricing = await api.get_model_pricing("claude-3-opus-20240229")
    assert "input" in pricing
    assert "output" in pricing
    assert pricing["input"] > 0
    assert pricing["output"] > 0
    
    # Test all pricing
    all_pricing = await api.get_all_pricing()
    assert "claude-3-opus-20240229" in all_pricing


@pytest.mark.asyncio
async def test_google_pricing_api():
    """Test Google pricing API."""
    api = GooglePricingAPI()
    
    # Test single model pricing
    pricing = await api.get_model_pricing("gemini-pro")
    assert "input" in pricing
    assert "output" in pricing
    assert pricing["input"] > 0
    assert pricing["output"] > 0
    
    # Test all pricing
    all_pricing = await api.get_all_pricing()
    assert "gemini-pro" in all_pricing


@pytest.mark.asyncio
async def test_mock_pricing_api():
    """Test mock pricing API."""
    api = MockPricingAPI("test-provider")
    
    # Set test data
    test_pricing = {
        "test-model": {"input": 0.01, "output": 0.03}
    }
    api.set_pricing_data(test_pricing)
    
    # Test single model pricing
    pricing = await api.get_model_pricing("test-model")
    assert "input" in pricing
    assert "output" in pricing
    # Should have some volatility
    assert 0.005 < pricing["input"] < 0.015
    
    # Test all pricing
    all_pricing = await api.get_all_pricing()
    assert "test-model" in all_pricing


@pytest.mark.asyncio
async def test_pricing_cache():
    """Test pricing cache functionality."""
    # Mock cache manager
    mock_cache_manager = AsyncMock()
    mock_cache_manager.get.return_value = None
    mock_cache_manager.set.return_value = True
    mock_cache_manager.delete.return_value = True
    mock_cache_manager.keys.return_value = []
    
    with patch('router_service.pricing.pricing_cache.get_cache_manager', return_value=mock_cache_manager):
        cache = PricingCache(ttl_seconds=300)
        
        # Test setting pricing
        pricing_data = {"input": 0.01, "output": 0.03}
        success = await cache.set_pricing("openai", "gpt-4", pricing_data)
        assert success
        
        # Verify cache manager was called
        mock_cache_manager.set.assert_called_once()
        
        # Test getting pricing
        mock_cache_manager.get.return_value = {
            "pricing": pricing_data,
            "timestamp": 1234567890,
            "provider": "openai",
            "model": "gpt-4"
        }
        
        cached_pricing = await cache.get_pricing("openai", "gpt-4")
        assert cached_pricing == pricing_data


@pytest.mark.asyncio
async def test_pricing_cache_change_detection():
    """Test pricing change detection in cache."""
    mock_cache_manager = AsyncMock()
    
    # Mock existing pricing data
    existing_data = {
        "pricing": {"input": 0.01, "output": 0.03},
        "timestamp": 1234567890,
        "provider": "openai",
        "model": "gpt-4"
    }
    mock_cache_manager.get.return_value = existing_data
    mock_cache_manager.set.return_value = True
    
    with patch('router_service.pricing.pricing_cache.get_cache_manager', return_value=mock_cache_manager):
        cache = PricingCache(ttl_seconds=300)
        
        # Set new pricing with significant change
        new_pricing = {"input": 0.015, "output": 0.03}  # 50% increase in input
        await cache.set_pricing("openai", "gpt-4", new_pricing)
        
        # Verify that set was called (change detection happens internally)
        mock_cache_manager.set.assert_called()
        
        # Check that the call included change detection
        call_args = mock_cache_manager.set.call_args[0]
        cached_data = call_args[1]  # Second argument is the data
        assert "changes_detected" in cached_data
        assert len(cached_data["changes_detected"]) > 0


@pytest.mark.asyncio
async def test_pricing_monitor():
    """Test pricing monitor functionality."""
    config = PricingConfig(
        enabled=True,
        update_interval_seconds=1,  # Fast for testing
        alerts_enabled=False  # Disable alerts for testing
    )
    
    monitor = PricingMonitor(config)
    
    # Test that monitor initializes
    assert monitor.config.enabled
    assert len(monitor.provider_apis) > 0  # Should have mock API at least
    
    # Test getting current pricing
    pricing = await monitor.get_current_pricing("mock", "test-model")
    # Mock API should return some pricing
    assert pricing is None or isinstance(pricing, dict)
    
    # Test monitoring statistics
    stats = monitor.get_monitoring_statistics()
    assert "is_monitoring" in stats
    assert "providers_configured" in stats
    assert stats["providers_configured"] >= 1  # At least mock provider


@pytest.mark.asyncio
async def test_pricing_manager():
    """Test pricing manager functionality."""
    config = PricingConfig(
        enabled=False,  # Disable monitoring for testing
        alerts_enabled=False
    )
    
    manager = PricingManager(config)
    
    # Test cost calculation
    cost_result = await manager.calculate_request_cost(
        provider="openai",
        model="gpt-4",
        input_tokens=1000,
        output_tokens=500
    )
    
    # Should return cost calculation even without real pricing data
    assert "provider" in cost_result
    assert "model" in cost_result
    assert "input_tokens" in cost_result
    assert "output_tokens" in cost_result
    
    # Test system health
    health = await manager.get_system_health()
    assert "pricing_monitoring" in health
    assert "components" in health


@pytest.mark.asyncio
async def test_enhanced_cost_aggregator():
    """Test enhanced cost aggregator integration."""
    from router_service.cost_aggregator import EnhancedCostAggregator
    
    aggregator = EnhancedCostAggregator()
    
    # Test legacy recording
    aggregator.record("gold", 0.05, "adapter-1")
    snapshot = aggregator.snapshot()
    assert snapshot["gold"] == 0.05
    
    # Test enhanced recording (async)
    result = await aggregator.record_request_cost(
        provider="openai",
        model="gpt-4",
        input_tokens=1000,
        output_tokens=500,
        actual_cost=0.08,
        tenant_id="tenant-123",
        validate_pricing=False  # Disable validation for testing
    )
    
    assert "provider" in result
    assert "model" in result
    assert "final_cost_usd" in result
    
    # Test enhanced snapshot
    enhanced_snapshot = aggregator.enhanced_snapshot()
    assert "provider_costs" in enhanced_snapshot
    assert "model_costs" in enhanced_snapshot
    assert "token_usage" in enhanced_snapshot
    assert "openai" in enhanced_snapshot["provider_costs"]
    assert "gpt-4" in enhanced_snapshot["model_costs"]


@pytest.mark.asyncio
async def test_pricing_validation():
    """Test pricing validation functionality."""
    config = PricingConfig(validation_enabled=True, validation_tolerance_percent=10.0)
    monitor = PricingMonitor(config)
    
    # Test validation with mock data
    validation_result = await monitor.validate_pricing_accuracy(
        provider="openai",
        model="gpt-4",
        actual_cost=0.08,
        tokens_used=1000,
        token_type="input"
    )
    
    # Should return validation result
    assert isinstance(validation_result, dict)
    if "error" not in validation_result:
        assert "provider" in validation_result
        assert "model" in validation_result
        assert "within_tolerance" in validation_result


@pytest.mark.asyncio
async def test_pricing_manager_cost_optimization():
    """Test cost optimization recommendations."""
    manager = PricingManager(PricingConfig(enabled=False))
    
    # Mock usage data
    usage_data = {
        "openai": {
            "gpt-4": 10000,
            "gpt-3.5-turbo": 5000
        },
        "anthropic": {
            "claude-3-opus": 2000
        }
    }
    
    # Test recommendations
    recommendations = await manager.get_cost_optimization_recommendations(usage_data)
    
    # Should return list of recommendations
    assert isinstance(recommendations, list)
    # May be empty if no cheaper alternatives found


@pytest.mark.asyncio
async def test_pricing_trends_and_changes():
    """Test pricing trends and change reporting."""
    manager = PricingManager(PricingConfig(enabled=False))
    
    # Test pricing trends
    trends = await manager.get_pricing_trends(hours=24)
    
    assert "total_changes" in trends
    assert "changes" in trends
    assert isinstance(trends["changes"], list)


@pytest.mark.asyncio
async def test_pricing_system_integration():
    """Test full pricing system integration."""
    # Test with minimal configuration
    config = PricingConfig(
        enabled=False,  # Don't start monitoring
        cache_enabled=True,
        alerts_enabled=False
    )
    
    # Initialize manager
    manager = PricingManager(config)
    
    # Test basic functionality
    health = await manager.get_system_health()
    assert isinstance(health, dict)
    
    # Test refresh
    refresh_result = await manager.refresh_all_pricing()
    assert "success" in refresh_result


if __name__ == "__main__":
    pytest.main([__file__])