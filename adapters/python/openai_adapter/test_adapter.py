#!/usr/bin/env python3
"""Test script for OpenAI adapter."""

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(__file__))

from server import OpenAIAdapter


class TestOpenAIAdapter:
    """Test cases for OpenAI adapter."""

    def setup_method(self):
        """Set up test fixtures."""
        self.adapter = OpenAIAdapter()

    def test_count_tokens(self):
        """Test token counting functionality."""
        # Test basic token counting
        text = "Hello, world!"
        model = "gpt-3.5-turbo"
        tokens = self.adapter._count_tokens(text, model)
        assert tokens > 0
        assert isinstance(tokens, int)

    def test_parse_prompt_json(self):
        """Test prompt JSON parsing."""
        # Test valid JSON
        prompt_json = json.dumps({
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello"}]
        })
        result = self.adapter._parse_prompt_json(prompt_json)
        assert result["model"] == "gpt-4"
        assert len(result["messages"]) == 1

        # Test invalid JSON (should fallback)
        invalid_json = "not valid json"
        result = self.adapter._parse_prompt_json(invalid_json)
        assert "messages" in result
        assert result["messages"][0]["content"] == invalid_json

    def test_estimate_output_tokens(self):
        """Test output token estimation."""
        # Test GPT-4
        tokens = self.adapter._estimate_output_tokens(1000, "gpt-4")
        assert tokens <= 4096
        assert tokens > 0

        # Test GPT-3.5
        tokens = self.adapter._estimate_output_tokens(1000, "gpt-3.5-turbo")
        assert tokens <= 4096
        assert tokens > 0

    def test_calculate_cost(self):
        """Test cost calculation."""
        cost = self.adapter._calculate_cost(1000, 500, "gpt-3.5-turbo")
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
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Hello, how are you?"}]
        }
        
        request = MockRequest(json.dumps(prompt_data))
        response = await self.adapter.Estimate(request, None)
        
        assert response.in_tokens > 0
        assert response.out_tokens > 0
        assert response.usd_micros > 0
        assert response.confidence > 0

    @pytest.mark.asyncio
    async def test_estimate_with_functions(self):
        """Test estimation with function calling."""
        class MockRequest:
            def __init__(self, prompt_json):
                self.prompt_json = prompt_json

        prompt_data = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "What's the weather?"}],
            "functions": [
                {
                    "name": "get_weather",
                    "description": "Get weather information",
                    "parameters": {
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
        assert "function_definitions_cost" in tool_breakdown

    @pytest.mark.asyncio
    async def test_health_check_no_api_key(self):
        """Test health check without API key."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove API key
            if "OPENAI_API_KEY" in os.environ:
                del os.environ["OPENAI_API_KEY"]
            
            adapter = OpenAIAdapter()
            
            class MockRequest:
                pass
            
            response = await adapter.Health(MockRequest(), None)
            assert response.error_rate > 0  # Should indicate error

    @pytest.mark.asyncio
    async def test_stream_no_api_key(self):
        """Test streaming without API key."""
        class MockRequest:
            def __init__(self, prompt_json):
                self.prompt_json = prompt_json

        prompt_data = {
            "model": "gpt-3.5-turbo",
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
        assert "OpenAI API key not configured" in content["error"]


def run_integration_tests():
    """Run integration tests if OpenAI API key is available."""
    if not os.getenv("OPENAI_API_KEY"):
        print("Skipping integration tests - OPENAI_API_KEY not set")
        return

    async def test_real_api():
        """Test with real OpenAI API."""
        adapter = OpenAIAdapter()
        
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
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Say hello in one word"}]
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