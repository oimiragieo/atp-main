# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""ATP Anthropic Adapter Service.

A gRPC-based adapter service that provides Anthropic Claude model interactions.
This adapter connects to Anthropic's API for AI model inference with support for:
- Claude-3 family models (Haiku, Sonnet, Opus)
- Function calling and tool use
- Streaming responses
- Vision capabilities
- Real-time cost tracking
"""

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any, Dict, List, Optional, Protocol

import adapter_pb2
import adapter_pb2_grpc
import anthropic
import grpc
import uvicorn
from fastapi import FastAPI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Anthropic pricing per 1K tokens (in USD micros - 1 USD = 1,000,000 micros)
ANTHROPIC_PRICING = {
    "claude-3-haiku-20240307": {"input": 250, "output": 1250},  # $0.00025/$0.00125 per 1K tokens
    "claude-3-sonnet-20240229": {"input": 3000, "output": 15000},  # $0.003/$0.015 per 1K tokens
    "claude-3-opus-20240229": {"input": 15000, "output": 75000},  # $0.015/$0.075 per 1K tokens
    "claude-3-5-sonnet-20241022": {"input": 3000, "output": 15000},  # $0.003/$0.015 per 1K tokens
    "claude-3-5-haiku-20241022": {"input": 1000, "output": 5000},  # $0.001/$0.005 per 1K tokens
    # Legacy models
    "claude-2.1": {"input": 8000, "output": 24000},  # $0.008/$0.024 per 1K tokens
    "claude-2.0": {"input": 8000, "output": 24000},  # $0.008/$0.024 per 1K tokens
    "claude-instant-1.2": {"input": 800, "output": 2400},  # $0.0008/$0.0024 per 1K tokens
}

# Default model if not specified
DEFAULT_MODEL = "claude-3-haiku-20240307"


class _AdapterServicerProto(Protocol):
    """Protocol for adapter servicer methods."""
    async def Estimate(self, req: adapter_pb2.EstimateRequest, ctx: Any) -> adapter_pb2.EstimateResponse: ...  # noqa: N802
    async def Stream(self, req: adapter_pb2.StreamRequest, ctx: Any) -> AsyncIterator[adapter_pb2.StreamChunk]: ...  # noqa: N802
    async def Health(self, req: adapter_pb2.HealthRequest, ctx: Any) -> adapter_pb2.HealthResponse: ...  # noqa: N802


class AnthropicAdapter:
    """Anthropic adapter implementation providing AI model interactions via Anthropic API."""

    def __init__(self):
        """Initialize the Anthropic adapter."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            self.client = anthropic.AsyncAnthropic(
                api_key=api_key,
                timeout=60.0,
            )
        else:
            # For testing without API key
            self.client = None
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using rough estimation.
        
        Anthropic doesn't provide a public tokenizer, so we use approximation.
        Claude uses a similar tokenizer to GPT models, roughly 4 chars per token.
        """
        return len(text) // 4 + 10  # Add small buffer for safety
    
    def _parse_prompt_json(self, prompt_json: str) -> Dict[str, Any]:
        """Parse the prompt JSON and extract relevant information."""
        try:
            prompt_data = json.loads(prompt_json)
            return prompt_data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse prompt JSON: {e}")
            return {"messages": [{"role": "user", "content": prompt_json}]}
    
    def _convert_messages_to_anthropic_format(self, messages: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
        """Convert OpenAI-style messages to Anthropic format.
        
        Anthropic expects a system prompt separate from messages, and messages
        must alternate between user and assistant.
        """
        system_prompt = ""
        anthropic_messages = []
        
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            
            if role == "system":
                system_prompt += content + "\n"
            elif role in ["user", "assistant"]:
                anthropic_messages.append({
                    "role": role,
                    "content": content
                })
        
        return system_prompt.strip(), anthropic_messages
    
    def _estimate_output_tokens(self, input_tokens: int, model: str) -> int:
        """Estimate output tokens based on input and model."""
        # Conservative estimates based on typical usage patterns
        if "opus" in model.lower():
            return min(input_tokens // 2, 4096)  # Opus tends to be more detailed
        elif "sonnet" in model.lower():
            return min(input_tokens // 3, 4096)  # Sonnet is balanced
        elif "haiku" in model.lower():
            return min(input_tokens // 4, 4096)  # Haiku is more concise
        else:
            return min(input_tokens // 3, 4096)  # Conservative default
    
    def _calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> int:
        """Calculate cost in USD micros."""
        pricing = ANTHROPIC_PRICING.get(model, ANTHROPIC_PRICING[DEFAULT_MODEL])
        
        input_cost = (input_tokens * pricing["input"]) // 1000
        output_cost = (output_tokens * pricing["output"]) // 1000
        
        return input_cost + output_cost

    async def Estimate(self, req: adapter_pb2.EstimateRequest, ctx: Any) -> adapter_pb2.EstimateResponse:  # noqa: N802
        """Estimate token usage and cost for a given prompt."""
        try:
            prompt_data = self._parse_prompt_json(req.prompt_json)
            model = prompt_data.get("model", DEFAULT_MODEL)
            
            # Count input tokens
            input_tokens = 0
            messages = prompt_data.get("messages", [])
            
            for message in messages:
                content = message.get("content", "")
                if isinstance(content, str):
                    input_tokens += self._count_tokens(content)
                elif isinstance(content, list):
                    # Handle multi-modal content (text + images)
                    for item in content:
                        if item.get("type") == "text":
                            input_tokens += self._count_tokens(item.get("text", ""))
                        elif item.get("type") == "image":
                            # Vision models: rough estimate for image processing
                            input_tokens += 1000  # Base cost for image analysis
            
            # Add tokens for tool definitions if present
            tools = prompt_data.get("tools", [])
            
            for tool in tools:
                tool_str = json.dumps(tool)
                input_tokens += self._count_tokens(tool_str)
            
            # Estimate output tokens
            max_tokens = prompt_data.get("max_tokens")
            if max_tokens:
                output_tokens = min(max_tokens, self._estimate_output_tokens(input_tokens, model))
            else:
                output_tokens = self._estimate_output_tokens(input_tokens, model)
            
            # Calculate cost
            cost_micros = self._calculate_cost(input_tokens, output_tokens, model)
            
            # Token estimates breakdown
            token_estimates = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "model": model,
                "breakdown": {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "tool_tokens": sum(self._count_tokens(json.dumps(t)) for t in tools),
                },
            }
            
            # Tool cost breakdown
            tool_cost_breakdown = {
                "tools_used": [tool.get("function", {}).get("name", "unknown") for tool in tools],
                "total_tool_cost_usd_micros": 0,  # Anthropic doesn't charge extra for tool use
                "tool_definitions_cost": sum(self._count_tokens(json.dumps(t)) for t in tools) * ANTHROPIC_PRICING.get(model, ANTHROPIC_PRICING[DEFAULT_MODEL])["input"] // 1000,
            }
            
            return adapter_pb2.EstimateResponse(
                in_tokens=input_tokens,
                out_tokens=output_tokens,
                usd_micros=cost_micros,
                confidence=0.8,  # Good confidence for Anthropic estimates
                tool_cost_breakdown_json=json.dumps(tool_cost_breakdown),
                token_estimates_json=json.dumps(token_estimates),
            )
            
        except Exception as e:
            logger.error(f"Error in Estimate: {e}")
            # Return fallback estimate
            fallback_tokens = len(req.prompt_json) // 4
            return adapter_pb2.EstimateResponse(
                in_tokens=fallback_tokens,
                out_tokens=fallback_tokens // 2,
                usd_micros=self._calculate_cost(fallback_tokens, fallback_tokens // 2, DEFAULT_MODEL),
                confidence=0.3,
                tool_cost_breakdown_json=json.dumps({"tools_used": [], "total_tool_cost_usd_micros": 0}),
                token_estimates_json=json.dumps({"input_tokens": fallback_tokens, "output_tokens": fallback_tokens // 2}),
            )

    async def Stream(self, req: adapter_pb2.StreamRequest, ctx: Any) -> AsyncIterator[adapter_pb2.StreamChunk]:  # noqa: N802
        """Stream response chunks for a given request."""
        try:
            if not self.client:
                yield adapter_pb2.StreamChunk(
                    type="agent.result.error",
                    content_json=json.dumps({
                        "error": "Anthropic API key not configured",
                        "adapter": "anthropic_adapter",
                        "error_type": "ConfigurationError",
                    }),
                    confidence=0.0,
                    partial_in_tokens=0,
                    partial_out_tokens=0,
                    partial_usd_micros=0,
                    more=False,
                )
                return
                
            prompt_data = self._parse_prompt_json(req.prompt_json)
            model = prompt_data.get("model", DEFAULT_MODEL)
            
            # Convert messages to Anthropic format
            system_prompt, anthropic_messages = self._convert_messages_to_anthropic_format(
                prompt_data.get("messages", [])
            )
            
            # Prepare Anthropic API call
            api_params = {
                "model": model,
                "messages": anthropic_messages,
                "stream": True,
                "max_tokens": prompt_data.get("max_tokens", 4096),
                "temperature": prompt_data.get("temperature", 0.7),
            }
            
            if system_prompt:
                api_params["system"] = system_prompt
            
            # Add tool use if present
            if "tools" in prompt_data:
                api_params["tools"] = prompt_data["tools"]
            
            # Track tokens and cost
            input_tokens = 0
            output_tokens = 0
            accumulated_content = ""
            tool_use_blocks = []
            
            # Count input tokens
            for message in anthropic_messages:
                content = message.get("content", "")
                if isinstance(content, str):
                    input_tokens += self._count_tokens(content)
            
            if system_prompt:
                input_tokens += self._count_tokens(system_prompt)
            
            start_time = time.time()
            
            async with self.client.messages.stream(**api_params) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        if hasattr(event.delta, 'text'):
                            text_delta = event.delta.text
                            accumulated_content += text_delta
                            output_tokens += self._count_tokens(text_delta)
                            
                            yield adapter_pb2.StreamChunk(
                                type="agent.result.partial",
                                content_json=json.dumps({
                                    "content": text_delta,
                                    "accumulated_content": accumulated_content,
                                    "model": model,
                                    "adapter": "anthropic_adapter"
                                }),
                                confidence=0.8,
                                partial_in_tokens=input_tokens,
                                partial_out_tokens=output_tokens,
                                partial_usd_micros=self._calculate_cost(input_tokens, output_tokens, model),
                                more=True,
                            )
                    
                    elif event.type == "content_block_start":
                        if hasattr(event.content_block, 'type') and event.content_block.type == "tool_use":
                            tool_use_blocks.append({
                                "id": event.content_block.id,
                                "name": event.content_block.name,
                                "input": {}
                            })
                    
                    elif event.type == "content_block_delta" and hasattr(event.delta, 'partial_json'):
                        # Handle tool use input streaming
                        if tool_use_blocks:
                            # Update the last tool use block with partial JSON
                            pass  # Anthropic handles this internally
                    
                    elif event.type == "message_stop":
                        # Get final usage statistics
                        message = await stream.get_final_message()
                        usage = message.usage
                        
                        final_content = {
                            "content": accumulated_content,
                            "model": model,
                            "adapter": "anthropic_adapter",
                            "stop_reason": message.stop_reason,
                            "usage": {
                                "input_tokens": usage.input_tokens,
                                "output_tokens": usage.output_tokens,
                                "total_tokens": usage.input_tokens + usage.output_tokens,
                            },
                            "response_time_ms": (time.time() - start_time) * 1000,
                        }
                        
                        if tool_use_blocks:
                            final_content["tool_calls"] = tool_use_blocks
                        
                        yield adapter_pb2.StreamChunk(
                            type="agent.result.final",
                            content_json=json.dumps(final_content),
                            confidence=0.9,
                            partial_in_tokens=usage.input_tokens,
                            partial_out_tokens=usage.output_tokens,
                            partial_usd_micros=self._calculate_cost(usage.input_tokens, usage.output_tokens, model),
                            more=False,
                        )
                        return
            
        except Exception as e:
            logger.error(f"Error in Stream: {e}")
            yield adapter_pb2.StreamChunk(
                type="agent.result.error",
                content_json=json.dumps({
                    "error": str(e),
                    "adapter": "anthropic_adapter",
                    "error_type": type(e).__name__,
                }),
                confidence=0.0,
                partial_in_tokens=0,
                partial_out_tokens=0,
                partial_usd_micros=0,
                more=False,
            )

    async def Health(self, req: adapter_pb2.HealthRequest, ctx: Any) -> adapter_pb2.HealthResponse:  # noqa: N802
        """Check health of the Anthropic adapter."""
        try:
            if not self.client:
                return adapter_pb2.HealthResponse(p95_ms=10000.0, error_rate=1.0)
                
            # Test Anthropic API connectivity with a minimal request
            start_time = time.time()
            
            response = await self.client.messages.create(
                model="claude-3-haiku-20240307",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=1,
                temperature=0,
            )
            
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            if response and response.content:
                return adapter_pb2.HealthResponse(p95_ms=response_time, error_rate=0.0)
            else:
                return adapter_pb2.HealthResponse(p95_ms=5000.0, error_rate=0.5)
                
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return adapter_pb2.HealthResponse(p95_ms=10000.0, error_rate=1.0)


# HTTP health endpoint
app = FastAPI()


@app.get("/health")
async def health() -> dict[str, Any]:
    """HTTP health endpoint."""
    try:
        # Quick health check
        if not os.getenv("ANTHROPIC_API_KEY"):
            return {"ok": False, "error": "ANTHROPIC_API_KEY not configured"}
        
        return {"ok": True, "adapter": "anthropic_adapter", "models_supported": list(ANTHROPIC_PRICING.keys())}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _register(server: grpc.aio.Server) -> None:
    """Register the adapter service with the gRPC server."""
    adapter_pb2_grpc.add_AdapterServiceServicer_to_server(AnthropicAdapter(), server)


async def serve() -> None:
    """Start the gRPC and HTTP servers."""
    # Validate configuration
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY environment variable is required")
        return
    
    # Start gRPC server
    grpc_server = grpc.aio.server()
    _register(grpc_server)
    grpc_server.add_insecure_port("[::]:7070")
    await grpc_server.start()
    logger.info("gRPC Anthropic Adapter listening on :7070")

    # Start HTTP server for health checks
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")  # noqa: S104
    http_server = uvicorn.Server(config)
    logger.info("HTTP Health server listening on :8080")

    # Run both servers concurrently
    await asyncio.gather(
        grpc_server.wait_for_termination(),
        http_server.serve()
    )


if __name__ == "__main__":
    asyncio.run(serve())