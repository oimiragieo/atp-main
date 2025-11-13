import json
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import the adapter protobuf
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../adapters/python/persona_adapter"))
import pytest

try:
    import adapter_pb2  # type: ignore
except Exception as e:  # pragma: no cover - environment-specific
    pytest.skip(f"Skipping adapter estimate extension tests due to import error: {e}", allow_module_level=True)


def test_estimate_extended_fields_presence():
    """Test that adapter estimate includes tool_cost_breakdown_json and token_estimates_json fields."""

    # Mock request
    req = adapter_pb2.EstimateRequest(
        stream_id="test-stream", task_type="test-task", prompt_json='{"prompt": "test prompt"}'
    )

    # Import the adapter server
    from adapters.python.persona_adapter.server import Adapter

    adapter = Adapter()

    # Mock context
    ctx = MagicMock()

    # Call estimate method
    import asyncio

    result = asyncio.run(adapter.Estimate(req, ctx))

    # Verify response has required fields
    assert hasattr(result, "tool_cost_breakdown_json")
    assert hasattr(result, "token_estimates_json")

    # Verify tool_cost_breakdown_json is valid JSON
    tool_breakdown = json.loads(result.tool_cost_breakdown_json)
    assert isinstance(tool_breakdown, dict)
    assert "tools_used" in tool_breakdown
    assert "total_tool_cost_usd_micros" in tool_breakdown

    # Verify token_estimates_json is valid JSON
    token_estimates = json.loads(result.token_estimates_json)
    assert isinstance(token_estimates, dict)
    assert "input_tokens" in token_estimates
    assert "output_tokens" in token_estimates
    assert "total_tokens" in token_estimates
    assert "breakdown" in token_estimates

    print("OK: Extended estimate fields test passed")


def test_estimate_token_estimates_structure():
    """Test that token_estimates has expected structure and values."""

    req = adapter_pb2.EstimateRequest(
        stream_id="test-stream", task_type="test-task", prompt_json='{"prompt": "test prompt"}'
    )

    from adapters.python.persona_adapter.server import Adapter

    adapter = Adapter()
    ctx = MagicMock()

    import asyncio

    result = asyncio.run(adapter.Estimate(req, ctx))

    token_estimates = json.loads(result.token_estimates_json)

    # Verify token counts are reasonable
    assert token_estimates["input_tokens"] > 0
    assert token_estimates["output_tokens"] > 0
    assert token_estimates["total_tokens"] == token_estimates["input_tokens"] + token_estimates["output_tokens"]

    # Verify breakdown structure
    breakdown = token_estimates["breakdown"]
    assert "prompt_tokens" in breakdown
    assert "completion_tokens" in breakdown
    assert breakdown["prompt_tokens"] == token_estimates["input_tokens"]
    assert breakdown["completion_tokens"] == token_estimates["output_tokens"]

    print("OK: Token estimates structure test passed")


def test_estimate_tool_cost_breakdown_structure():
    """Test that tool_cost_breakdown has expected structure."""

    req = adapter_pb2.EstimateRequest(
        stream_id="test-stream", task_type="test-task", prompt_json='{"prompt": "test prompt"}'
    )

    from adapters.python.persona_adapter.server import Adapter

    adapter = Adapter()
    ctx = MagicMock()

    import asyncio

    result = asyncio.run(adapter.Estimate(req, ctx))

    tool_breakdown = json.loads(result.tool_cost_breakdown_json)

    # Verify structure
    assert isinstance(tool_breakdown["tools_used"], list)
    assert isinstance(tool_breakdown["total_tool_cost_usd_micros"], int)
    assert tool_breakdown["total_tool_cost_usd_micros"] >= 0

    print("OK: Tool cost breakdown structure test passed")


if __name__ == "__main__":
    test_estimate_extended_fields_presence()
    test_estimate_token_estimates_structure()
    test_estimate_tool_cost_breakdown_structure()
    print("All GAP-119 estimate extension tests passed!")
