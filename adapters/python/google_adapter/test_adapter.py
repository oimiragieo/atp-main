#!/usr/bin/env python3
"""Test script for Google AI adapter."""

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(__file__))

from server import GoogleAdapter


class TestGoogleAdapter:
    """Test cases for Google AI adapter."""

    def setup_method(self):
        """Set up test fixtures."""
        self.adapter = GoogleAdapter()

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
            "model": "gemini-1.5-flash",
            "messages": [{"role": "user", "content": "Hello"}]
        })
        result = self.adapter._parse_prompt_json(prompt_json)
        assert result["model"] == "gemini-1.5-flash"
        assert len(result["messages"]) == 1

        # Test invalid JSON (should fallback)
        invalid_json = "not valid json"
        result = self.adapter._parse_prompt_json(invalid_json)
        assert "messages" in result
        assert result["messages"][0]["content"] == invalid_json

    def test_convert_messages_to_google_format(self):
        """Test message format conversion."""
        # Test with various message types
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"}
        ]
        
        google_messages = self.adapter._convert_messages_to_google_format(messages)
        
        # System messages are filtered out (handled separately)
        assert len(google_messages) == 3
        assert google_messages[0]["role"] == "user"
        assert google_messages[1]["role"] == "model"  # assistant -> model
        assert google_messages[2]["role"] == "user"
        
        # Check parts format
        assert "parts" in google_messages[0]
        assert google_messages[0]["parts"][0]["text"] == "Hello"

    def test_extract_system_prompt(self):
        """Test system prompt extraction."""
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "system", "content": "Be concise"}
        ]
        
        system_prompt = self.adapter._extract_system_prompt(messages)
        assert "You are helpful" in system_prompt
        assert "Be concise" in system_prompt

    def test_estimate_output_tokens(self):
        """Test output token estimation."""
        # Test different models
        tokens_pro = self.adapter._estimate_output_tokens(1000, "gemini-1.5-pro")
        tokens_flash = self.adapter._estimate_output_tokens(1000, "gemini-1.5-flash")
        
        assert tokens_pro <= 8192
        assert tokens_flash <= 8192
        assert tokens_pro > 0
        assert tokens_flash > 0

    def test_calculate_cost(self):
        """Test cost calculation."""
        cost = self.adapter._calculate_cost(1000, 500, "gemini-1.5-flash")
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
            "model": "gemini-1.5-flash",
            "messages": [{"role": "user", "content": "Hello, how are you?"}]
        }
        
        request = MockRequest(json.dumps(prompt_data))
        response = await self.adapter.Estimate(request, None)
        
        assert response.in_tokens > 0
        assert response.out_tokens > 0
        assert response.usd_micros >= 0  # Google AI can be very cheap
        assert response.confidence > 0

    @pytest.mark.asyncio
    async def test_estimate_with_multimodal(self):
        """Test estimation with multi-modal content."""
        class MockRequest:
            def __init__(self, prompt_json):
                self.prompt_json = prompt_json

        prompt_data = {
            "model": "gemini-1.5-pro",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What's in this image?"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": "fake-base64-data"
                            }
                        }
                    ]
                }
            ]
        }
        
        request = MockRequest(json.dumps(prompt_data))
        response = await self.adapter.Estimate(request, None)
        
        assert response.in_tokens > 0
        assert response.out_tokens > 0
        assert response.usd_micros >= 0
        
        # Should include image processing tokens
        token_estimates = json.loads(response.token_estimates_json)
        assert token_estimates["input_tokens"] > 10  # Should include image tokens

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
            "model": "gemini-1.5-flash",
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
        assert "Google API key not configured" in content["error"]


def run_integration_tests():
    """Run integration tests if Google API key is available."""
    if not os.getenv("GOOGLE_API_KEY"):
        print("Skipping integration tests - GOOGLE_API_KEY not set")
        return

    async def test_real_api():
        """Test with real Google AI API."""
        adapter = GoogleAdapter()
        
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
            "model": "gemini-1.5-flash",
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