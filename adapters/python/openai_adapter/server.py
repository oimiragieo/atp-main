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

"""ATP OpenAI Adapter Service.

A gRPC-based adapter service that provides OpenAI model interactions.
This adapter connects to OpenAI's API for AI model inference with support for:
- GPT-4 and GPT-3.5 models
- Function calling and tool use
- Streaming responses
- Vision models (GPT-4V)
- Embeddings
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
import grpc
import openai
import tiktoken
import uvicorn
from fastapi import FastAPI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OpenAI pricing per 1K tokens (in USD micros - 1 USD = 1,000,000 micros)
OPENAI_PRICING = {
    "gpt-4": {"input": 30000, "output": 60000},  # $0.03/$0.06 per 1K tokens
    "gpt-4-32k": {"input": 60000, "output": 120000},  # $0.06/$0.12 per 1K tokens
    "gpt-4-turbo": {"input": 10000, "output": 30000},  # $0.01/$0.03 per 1K tokens
    "gpt-4-turbo-preview": {"input": 10000, "output": 30000},
    "gpt-4-vision-preview": {"input": 10000, "output": 30000},
    "gpt-3.5-turbo": {"input": 500, "output": 1500},  # $0.0005/$0.0015 per 1K tokens
    "gpt-3.5-turbo-16k": {"input": 3000, "output": 4000},  # $0.003/$0.004 per 1K tokens
    "text-embedding-ada-002": {"input": 100, "output": 0},  # $0.0001 per 1K tokens
    "text-embedding-3-small": {"input": 20, "output": 0},  # $0.00002 per 1K tokens
    "text-embedding-3-large": {"input": 130, "output": 0},  # $0.00013 per 1K tokens
}

# Default model if not specified
DEFAULT_MODEL = "gpt-3.5-turbo"


class _AdapterServicerProto(Protocol):
    """Protocol for adapter servicer methods."""
    async def Estimate(self, req: adapter_pb2.EstimateRequest, ctx: Any) -> adapter_pb2.EstimateResponse: ...  # noqa: N802
    async def Stream(self, req: adapter_pb2.StreamRequest, ctx: Any) -> AsyncIterator[adapter_pb2.StreamChunk]: ...  # noqa: N802
    async def Health(self, req: adapter_pb2.HealthRequest, ctx: Any) -> adapter_pb2.HealthResponse: ...  # noqa: N802


class OpenAIAdapter:
    """OpenAI adapter implementation providing AI model interactions via OpenAI API."""

    def __init__(self):
        """Initialize the OpenAI adapter."""
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            self.client = openai.AsyncOpenAI(
                api_key=api_key,
                timeout=60.0,
            )
        else:
            # For testing without API key
            self.client = None
        self.encoding_cache = {}
        
    def _get_encoding(self, model: str) -> tiktoken.Encoding:
        """Get tiktoken encoding for a model, with caching."""
        if model not in self.encoding_cache:
            try:
                self.encoding_cache[model] = tiktoken.encoding_for_model(model)
            except KeyError:
                # Fallback to cl100k_base for unknown models
                self.encoding_cache[model] = tiktoken.get_encoding("cl100k_base")
        return self.encoding_cache[model]
    
    def _count_tokens(self, text: str, model: str) -> int:
        """Count tokens in text using tiktoken."""
        try:
            encoding = self._get_encoding(model)
            return len(encoding.encode(text))
        except Exception as e:
            logger.warning(f"Failed to count tokens for model {model}: {e}")
            # Fallback to rough estimation
            return len(text) // 4
    
    def _parse_prompt_json(self, prompt_json: str) -> Dict[str, Any]:
        """Parse the prompt JSON and extract relevant information."""
        try:
            prompt_data = json.loads(prompt_json)
            return prompt_data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse prompt JSON: {e}")
            return {"messages": [{"role": "user", "content": prompt_json}]}
    
    def _estimate_output_tokens(self, input_tokens: int, model: str) -> int:
        """Estimate output tokens based on input and model."""
        # Conservative estimates based on typical usage patterns
        if "gpt-4" in model:
            return min(input_tokens // 2, 4096)  # GPT-4 tends to be more concise
        elif "gpt-3.5" in model:
            return min(input_tokens // 3, 4096)  # GPT-3.5 can be more verbose
        else:
            return min(input_tokens // 4, 2048)  # Conservative default
    
    def _calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> int:
        """Calculate cost in USD micros."""
        pricing = OPENAI_PRICING.get(model, OPENAI_PRICING[DEFAULT_MODEL])
        
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
                    input_tokens += self._count_tokens(content, model)
                elif isinstance(content, list):
                    # Handle multi-modal content (text + images)
                    for item in content:
                        if item.get("type") == "text":
                            input_tokens += self._count_tokens(item.get("text", ""), model)
                        elif item.get("type") == "image_url":
                            # Vision models: rough estimate for image processing
                            input_tokens += 765  # Base cost for image analysis
            
            # Add tokens for function definitions if present
            functions = prompt_data.get("functions", [])
            tools = prompt_data.get("tools", [])
            
            for func in functions:
                func_str = json.dumps(func)
                input_tokens += self._count_tokens(func_str, model)
            
            for tool in tools:
                tool_str = json.dumps(tool)
                input_tokens += self._count_tokens(tool_str, model)
            
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
                    "function_tokens": sum(self._count_tokens(json.dumps(f), model) for f in functions),
                    "tool_tokens": sum(self._count_tokens(json.dumps(t), model) for t in tools),
                },
            }
            
            # Tool cost breakdown
            tool_cost_breakdown = {
                "tools_used": [tool.get("function", {}).get("name", "unknown") for tool in tools],
                "total_tool_cost_usd_micros": 0,  # OpenAI doesn't charge extra for function calls
                "function_definitions_cost": sum(self._count_tokens(json.dumps(f), model) for f in functions) * OPENAI_PRICING.get(model, OPENAI_PRICING[DEFAULT_MODEL])["input"] // 1000,
            }
            
            return adapter_pb2.EstimateResponse(
                in_tokens=input_tokens,
                out_tokens=output_tokens,
                usd_micros=cost_micros,
                confidence=0.9,  # High confidence for OpenAI estimates
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
                        "error": "OpenAI API key not configured",
                        "adapter": "openai_adapter",
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
            
            # Prepare OpenAI API call
            api_params = {
                "model": model,
                "messages": prompt_data.get("messages", []),
                "stream": True,
                "temperature": prompt_data.get("temperature", 0.7),
                "max_tokens": prompt_data.get("max_tokens"),
            }
            
            # Add function calling if present
            if "functions" in prompt_data:
                api_params["functions"] = prompt_data["functions"]
                if "function_call" in prompt_data:
                    api_params["function_call"] = prompt_data["function_call"]
            
            if "tools" in prompt_data:
                api_params["tools"] = prompt_data["tools"]
                if "tool_choice" in prompt_data:
                    api_params["tool_choice"] = prompt_data["tool_choice"]
            
            # Remove None values
            api_params = {k: v for k, v in api_params.items() if v is not None}
            
            # Track tokens and cost
            input_tokens = 0
            output_tokens = 0
            accumulated_content = ""
            function_call_data = None
            tool_calls = []
            
            # Count input tokens
            for message in prompt_data.get("messages", []):
                content = message.get("content", "")
                if isinstance(content, str):
                    input_tokens += self._count_tokens(content, model)
            
            start_time = time.time()
            
            async for chunk in await self.client.chat.completions.create(**api_params):
                if chunk.choices and len(chunk.choices) > 0:
                    choice = chunk.choices[0]
                    delta = choice.delta
                    
                    # Handle regular content
                    if delta.content:
                        accumulated_content += delta.content
                        output_tokens += self._count_tokens(delta.content, model)
                        
                        yield adapter_pb2.StreamChunk(
                            type="agent.result.partial",
                            content_json=json.dumps({
                                "content": delta.content,
                                "accumulated_content": accumulated_content,
                                "model": model,
                                "adapter": "openai_adapter"
                            }),
                            confidence=0.8,
                            partial_in_tokens=input_tokens,
                            partial_out_tokens=output_tokens,
                            partial_usd_micros=self._calculate_cost(input_tokens, output_tokens, model),
                            more=True,
                        )
                    
                    # Handle function calls
                    if delta.function_call:
                        if function_call_data is None:
                            function_call_data = {"name": "", "arguments": ""}
                        
                        if delta.function_call.name:
                            function_call_data["name"] += delta.function_call.name
                        if delta.function_call.arguments:
                            function_call_data["arguments"] += delta.function_call.arguments
                    
                    # Handle tool calls
                    if delta.tool_calls:
                        for tool_call in delta.tool_calls:
                            # Extend tool_calls list if needed
                            while len(tool_calls) <= tool_call.index:
                                tool_calls.append({"id": "", "type": "", "function": {"name": "", "arguments": ""}})
                            
                            if tool_call.id:
                                tool_calls[tool_call.index]["id"] = tool_call.id
                            if tool_call.type:
                                tool_calls[tool_call.index]["type"] = tool_call.type
                            if tool_call.function:
                                if tool_call.function.name:
                                    tool_calls[tool_call.index]["function"]["name"] += tool_call.function.name
                                if tool_call.function.arguments:
                                    tool_calls[tool_call.index]["function"]["arguments"] += tool_call.function.arguments
                    
                    # Check if this is the final chunk
                    if choice.finish_reason:
                        final_content = {
                            "content": accumulated_content,
                            "model": model,
                            "adapter": "openai_adapter",
                            "finish_reason": choice.finish_reason,
                            "usage": {
                                "prompt_tokens": input_tokens,
                                "completion_tokens": output_tokens,
                                "total_tokens": input_tokens + output_tokens,
                            },
                            "response_time_ms": (time.time() - start_time) * 1000,
                        }
                        
                        if function_call_data:
                            final_content["function_call"] = function_call_data
                        
                        if tool_calls:
                            final_content["tool_calls"] = tool_calls
                        
                        yield adapter_pb2.StreamChunk(
                            type="agent.result.final",
                            content_json=json.dumps(final_content),
                            confidence=0.9,
                            partial_in_tokens=input_tokens,
                            partial_out_tokens=output_tokens,
                            partial_usd_micros=self._calculate_cost(input_tokens, output_tokens, model),
                            more=False,
                        )
                        return
            
        except Exception as e:
            logger.error(f"Error in Stream: {e}")
            yield adapter_pb2.StreamChunk(
                type="agent.result.error",
                content_json=json.dumps({
                    "error": str(e),
                    "adapter": "openai_adapter",
                    "error_type": type(e).__name__,
                }),
                confidence=0.0,
                partial_in_tokens=0,
                partial_out_tokens=0,
                partial_usd_micros=0,
                more=False,
            )

    async def Health(self, req: adapter_pb2.HealthRequest, ctx: Any) -> adapter_pb2.HealthResponse:  # noqa: N802
        """Check health of the OpenAI adapter."""
        try:
            if not self.client:
                return adapter_pb2.HealthResponse(p95_ms=10000.0, error_rate=1.0)
                
            # Test OpenAI API connectivity with a minimal request
            start_time = time.time()
            
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=1,
                temperature=0,
            )
            
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            if response and response.choices:
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
        client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Just check if we can create a client and have an API key
        if not os.getenv("OPENAI_API_KEY"):
            return {"ok": False, "error": "OPENAI_API_KEY not configured"}
        
        return {"ok": True, "adapter": "openai_adapter", "models_supported": list(OPENAI_PRICING.keys())}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _register(server: grpc.aio.Server) -> None:
    """Register the adapter service with the gRPC server."""
    adapter_pb2_grpc.add_AdapterServiceServicer_to_server(OpenAIAdapter(), server)


async def serve() -> None:
    """Start the gRPC and HTTP servers."""
    # Validate configuration
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY environment variable is required")
        return
    
    # Start gRPC server
    grpc_server = grpc.aio.server()
    _register(grpc_server)
    grpc_server.add_insecure_port("[::]:7070")
    await grpc_server.start()
    logger.info("gRPC OpenAI Adapter listening on :7070")

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