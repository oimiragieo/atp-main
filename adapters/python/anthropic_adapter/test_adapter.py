#!/usr/bin/env python3
"""Test script for Anthropic adapter."""

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(__file__))

from server import AnthropicAdapter


class TestAnthropicAdapter:
    """Test cases for Anthropic adapter."""

    def setup_method(self):
        """Set up test fixtures."""
        self.adapter = AnthropicAdapter()

    def test_count_tokens(self):
        """Test token counting functionality."""
        # Test basic token counting
        text = "Hello, world!"
        tokens = self.adapter._count_tokens(text)
        assert tokens > 0
        assert isinstance(tokens, int)

    def test_parse_prompt_json(self):
        """Test prompt JSON parsing."""
        # Test valid JSON
        prompt_json = json.dumps({
            "model": "claude-3-haiku-20240307",
            "messages": [{"role": "user", "content": "Hello"}]
        })
        result = self.adapter._parse_prompt_json(prompt_json)
        assert result["model"] == "claude-3-haiku-20240307"
        assert len(result["messages"]) == 1

        # Test invalid JSON (should fallback)
        invalid_json = "not valid json"
        result = self.adapter._parse_prompt_json(invalid_json)
        assert "messages" in result
        assert result["messages"][0]["content"] == invalid_json

    def test_convert_messages_to_anthropic_format(self):
        """Test message format conversion."""
        # Test with system message
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"}
        ]
        
        system_prompt, anthropic_messages = self.adapter._convert_messages_to_anthropic_format(messages)
        
        assert system_prompt == "You are helpful"
        assert len(anthropic_messages) == 3
        assert anthropic_messages[0]["role"] == "user"
        assert anthropic_messages[1]["role"] == "assistant"
        assert anthropic_messages[2]["role"] == "user"

    def test_estimate_output_tokens(self):
        """Test output token estimation."""
        # Test different models
        tokens_opus = self.adapter._estimate_output_tokens(1000, "claude-3-opus-20240229")
        tokens_sonnet = self.adapter._estimate_output_tokens(1000, "claude-3-sonnet-20240229")
        tokens_haiku = self.adapter._estimate_output_tokens(1000, "claude-3-haiku-20240307")
        
        assert tokens_opus <= 4096
        assert tokens_sonnet <= 4096
        assert tokens_haiku <= 4096
        assert tokens_opus > 0
        assert tokens_sonnet > 0
        assert tokens_haiku > 0

    def test_calculate_cost(self):
        """Test cost calculation."""
        cost = self.adapter._calculate_cost(1000, 500, "claude-3-haiku-20240307")
        assert cost > 0
        assert isinstance(cost, int)

        # Test with unknown model (should use default)
        cost = self.adapter._calculate_cost(1000, 500, "unknown-model")
        assert cost > 0

    @pytest.mark.asyncio
    async def test_estimate_basic(self):
        """Test basic estimation functionality."""
        # Create a mock request
        class MockRequest:
            def __init__(self, prompt_json):
                self.prompt_json = prompt_json

        prompt_data = {
            "model": "claude-3-haiku-20240307",
            "messages": [{"role": "user", "content": "Hello, how are you?"}]
        }
        
        request = MockRequest(json.dumps(prompt_data))
        response = await self.adapter.Estimate(request, None)
        
        assert response.in_tokens > 0
        assert response.out_tokens > 0
        assert response.usd_micros > 0
        assert response.confidence > 0

    @pytest.mark.asyncio
    async def test_estimate_with_tools(self):
        """Test estimation with tool use."""
        class MockRequest:
            def __init__(self, prompt_json):
                self.prompt_json = prompt_json

        prompt_data = {
            "model": "claude-3-sonnet-20240229",
            "messages": [{"role": "user", "content": "What's the weather?"}],
            "tools": [
                {
                    "name": "get_weather",
                    "description": "Get weather information",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"}
                        }
                    }
                }
            ]
        }
        
        request = MockRequest(json.dumps(prompt_data))
        response = await self.adapter.Estimate(request, None)
        
        assert response.in_tokens > 0
        assert response.out_tokens > 0
        assert response.usd_micros > 0
        
        # Check tool cost breakdown
        tool_breakdown = json.loads(response.tool_cost_breakdown_json)
        assert "tool_definitions_cost" in tool_breakdown

    @pytest.mark.asyncio
    async def test_health_check_no_api_key(self):
        """Test health check without API key."""
        class MockRequest:
            pass
        
        response = await self.adapter.Health(MockRequest(), None)
        assert response.error_rate > 0  # Should indicate error

    @pytest.mark.asyncio
    async def test_stream_no_api_key(self):
        """Test streaming without API key."""
        class MockRequest:
            def __init__(self, prompt_json):
                self.prompt_json = prompt_json

        prompt_data = {
            "model": "claude-3-haiku-20240307",
            "messages": [{"role": "user", "content": "Hello"}]
        }
        
        request = MockRequest(json.dumps(prompt_data))
        
        chunks = []
        async for chunk in self.adapter.Stream(request, None):
            chunks.append(chunk)
        
        assert len(chunks) == 1  # Should have one error chunk
        
        # Check error chunk
        error_chunk = chunks[0]
        assert error_chunk.type == "agent.result.error"
        assert not error_chunk.more
        
        content = json.loads(error_chunk.content_json)
        assert "error" in content
        assert "Anthropic API key not configured" in content["error"]


def run_integration_tests():
    """Run integration tests if Anthropic API key is available."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Skipping integration tests - ANTHROPIC_API_KEY not set")
        return

    async def test_real_api():
        """Test with real Anthropic API."""
        adapter = AnthropicAdapter()
        
        # Test health check
        class MockRequest:
            pass
        
        health_response = await adapter.Health(MockRequest(), None)
        print(f"Health check - P95: {health_response.p95_ms}ms, Error rate: {health_response.error_rate}")
        
        # Test estimation
        class MockEstimateRequest:
            def __init__(self, prompt_json):
                self.prompt_json = prompt_json
        
        prompt_data = {
            "model": "claude-3-haiku-20240307",
            "messages": [{"role": "user", "content": "Say hello in one word"}],
            "max_tokens": 10
        }
        
        estimate_request = MockEstimateRequest(json.dumps(prompt_data))
        estimate_response = await adapter.Estimate(estimate_request, None)
        
        print(f"Estimation - Input: {estimate_response.in_tokens}, Output: {estimate_response.out_tokens}, Cost: ${estimate_response.usd_micros/1000000:.6f}")
        
        # Test streaming (with a very short response to minimize cost)
        class MockStreamRequest:
            def __init__(self, prompt_json):
                self.prompt_json = prompt_json
        
        stream_request = MockStreamRequest(json.dumps(prompt_data))
        
        print("Streaming response:")
        async for chunk in adapter.Stream(stream_request, None):
            content = json.loads(chunk.content_json)
            if chunk.type == "agent.result.partial" and "content" in content:
                print(f"  Chunk: {content['content']}")
            elif chunk.type == "agent.result.final":
                print(f"  Final: {content.get('content', 'N/A')}")
                print(f"  Usage: {content.get('usage', {})}")
                break
    
    asyncio.run(test_real_api())


if __name__ == "__main__":
    # Run unit tests
    pytest.main([__file__, "-v"])
    
    # Run integration tests if API key is available
    print("\n" + "="*50)
    print("Running integration tests...")
    run_integration_tests()