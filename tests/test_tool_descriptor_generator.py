"""Tests for tool descriptor generator from adapter registry (GAP-126)."""

from __future__ import annotations

from metrics.registry import REGISTRY
from router_service.capability_handler import generate_tool_descriptors, get_capability_handler


def test_generate_tool_descriptors_empty_registry():
    """Test tool descriptor generation with empty adapter registry."""
    # Clear any existing adapters for this test
    handler = get_capability_handler()
    original_adapters = handler.registry.get_all_adapters()
    
    # Temporarily clear registry
    handler.registry._adapters.clear()
    handler.registry._adapter_types.clear()
    
    try:
        tools = generate_tool_descriptors()
        
        # Should always have at least the route.complete tool
        assert len(tools) >= 1
        assert tools[0]["name"] == "route.complete"
        assert "Adaptive completion" in tools[0]["description"]
        assert "prompt" in tools[0]["inputSchema"]["required"]
        
        # Check metrics
        tools_exposed = REGISTRY.gauge("tools_exposed_total")
        assert tools_exposed.value == len(tools)
        
    finally:
        # Restore original adapters
        for adapter in original_adapters:
            handler.registry.register_capability({
                "adapter_id": adapter.adapter_id,
                "adapter_type": adapter.adapter_type,
                "capabilities": adapter.capabilities,
                "models": adapter.models,
                "max_tokens": adapter.max_tokens,
                "version": adapter.version,
            })


def test_generate_tool_descriptors_with_adapters():
    """Test tool descriptor generation with registered adapters."""
    handler = get_capability_handler()
    
    # Register a test adapter
    test_adapter_data = {
        "adapter_id": "test-ollama-adapter",
        "adapter_type": "text-generation",
        "capabilities": ["text-generation", "embedding"],
        "models": ["llama2:7b", "codellama:13b"],
        "max_tokens": 4096,
        "version": "1.0.0",
    }
    
    success = handler.registry.register_capability(test_adapter_data)
    assert success
    
    try:
        tools = generate_tool_descriptors()
        
        # Should have route.complete + adapter-specific tool
        assert len(tools) >= 2
        
        # Check route.complete tool
        route_tool = next((t for t in tools if t["name"] == "route.complete"), None)
        assert route_tool is not None
        assert "adapter_type" in route_tool["inputSchema"]["properties"]
        
        # Check adapter-specific tool
        adapter_tool = next((t for t in tools if t["name"] == "adapter.test-ollama-adapter"), None)
        assert adapter_tool is not None
        assert "Direct access to test-ollama-adapter" in adapter_tool["description"]
        assert adapter_tool["inputSchema"]["properties"]["max_tokens"]["default"] == 4096
        assert "llama2:7b" in adapter_tool["inputSchema"]["properties"]["model"]["enum"]
        
        # Check metrics
        tools_exposed = REGISTRY.gauge("tools_exposed_total")
        assert tools_exposed.value == len(tools)
        
    finally:
        # Clean up test adapter
        handler.registry.unregister_adapter("test-ollama-adapter")


def test_generate_tool_descriptors_unhealthy_adapter():
    """Test that unhealthy adapters are not included in tool descriptors."""
    handler = get_capability_handler()
    
    # Register a test adapter
    test_adapter_data = {
        "adapter_id": "test-unhealthy-adapter",
        "adapter_type": "text-generation",
        "capabilities": ["text-generation"],
        "models": ["test-model"],
        "max_tokens": 1024,
        "version": "1.0.0",
    }
    
    success = handler.registry.register_capability(test_adapter_data)
    assert success
    
    # Get the adapter and make it unhealthy by setting old last_seen
    adapter = handler.registry.get_adapter("test-unhealthy-adapter")
    assert adapter is not None
    adapter.last_seen = 0  # Very old timestamp
    
    try:
        tools = generate_tool_descriptors()
        
        # Should have route.complete but not the unhealthy adapter tool
        route_tool = next((t for t in tools if t["name"] == "route.complete"), None)
        assert route_tool is not None
        
        unhealthy_tool = next((t for t in tools if t["name"] == "adapter.test-unhealthy-adapter"), None)
        assert unhealthy_tool is None  # Should not be included
        
    finally:
        # Clean up test adapter
        handler.registry.unregister_adapter("test-unhealthy-adapter")


def test_tool_descriptor_schema_completeness():
    """Test that generated tool descriptors have complete and valid schemas."""
    handler = get_capability_handler()
    
    # Register a comprehensive test adapter
    test_adapter_data = {
        "adapter_id": "test-comprehensive-adapter",
        "adapter_type": "multimodal",
        "capabilities": ["text-generation", "image-generation", "embedding"],
        "models": ["gpt-4", "dall-e-3", "text-embedding-ada-002"],
        "max_tokens": 8192,
        "supported_languages": ["en", "es", "fr"],
        "version": "2.1.0",
    }
    
    success = handler.registry.register_capability(test_adapter_data)
    assert success
    
    try:
        tools = generate_tool_descriptors()
        
        # Find the adapter tool
        adapter_tool = next((t for t in tools if t["name"] == "adapter.test-comprehensive-adapter"), None)
        assert adapter_tool is not None
        
        # Validate schema completeness
        schema = adapter_tool["inputSchema"]
        assert schema["type"] == "object"
        assert "prompt" in schema["required"]
        
        properties = schema["properties"]
        assert "prompt" in properties
        assert properties["prompt"]["type"] == "string"
        
        assert "max_tokens" in properties
        assert properties["max_tokens"]["type"] == "integer"
        assert properties["max_tokens"]["default"] == 8192
        
        assert "model" in properties
        assert properties["model"]["type"] == "string"
        assert "gpt-4" in properties["model"]["enum"]
        assert "dall-e-3" in properties["model"]["enum"]
        
    finally:
        # Clean up test adapter
        handler.registry.unregister_adapter("test-comprehensive-adapter")


def test_metrics_tools_exposed_total():
    """Test that tools_exposed_total metric is properly updated."""
    # Generate tools (this should update the metric)
    tools = generate_tool_descriptors()

    # Check that metric was updated
    final_value = REGISTRY.gauge("tools_exposed_total").value
    assert final_value == len(tools)
    assert final_value >= 1  # At minimum should have route.complete