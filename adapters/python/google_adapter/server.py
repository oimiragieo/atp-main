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

"""ATP Google AI Adapter Service.

A gRPC-based adapter service that provides Google AI (Gemini) model interactions.
This adapter connects to Google's Generative AI API for AI model inference with support for:
- Gemini Pro and Ultra models
- Multi-modal capabilities (text, vision, audio)
- Function calling and tool use
- Streaming responses
- Real-time cost tracking
"""

import asyncio
import base64
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any, Protocol

import adapter_pb2
import adapter_pb2_grpc
import google.generativeai as genai
import grpc
import uvicorn
from fastapi import FastAPI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Google AI pricing per 1K tokens (in USD micros - 1 USD = 1,000,000 micros)
GOOGLE_PRICING = {
    "gemini-1.5-pro": {"input": 3500, "output": 10500},  # $0.0035/$0.0105 per 1K tokens
    "gemini-1.5-flash": {"input": 75, "output": 300},  # $0.000075/$0.0003 per 1K tokens
    "gemini-1.0-pro": {"input": 500, "output": 1500},  # $0.0005/$0.0015 per 1K tokens
    "gemini-1.0-pro-vision": {"input": 250, "output": 500},  # $0.00025/$0.0005 per 1K tokens
    "gemini-pro": {"input": 500, "output": 1500},  # Alias for gemini-1.0-pro
    "gemini-pro-vision": {"input": 250, "output": 500},  # Alias for gemini-1.0-pro-vision
    # Text embedding models
    "text-embedding-004": {"input": 10, "output": 0},  # $0.00001 per 1K tokens
    "embedding-001": {"input": 10, "output": 0},  # $0.00001 per 1K tokens (legacy)
}

# Default model if not specified
DEFAULT_MODEL = "gemini-1.5-flash"


class _AdapterServicerProto(Protocol):
    """Protocol for adapter servicer methods."""

    async def Estimate(self, req: adapter_pb2.EstimateRequest, ctx: Any) -> adapter_pb2.EstimateResponse: ...  # noqa: N802
    async def Stream(self, req: adapter_pb2.StreamRequest, ctx: Any) -> AsyncIterator[adapter_pb2.StreamChunk]: ...  # noqa: N802
    async def Health(self, req: adapter_pb2.HealthRequest, ctx: Any) -> adapter_pb2.HealthResponse: ...  # noqa: N802


class GoogleAdapter:
    """Google AI adapter implementation providing AI model interactions via Google Generative AI API."""

    def __init__(self):
        """Initialize the Google AI adapter."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            self.configured = True
        else:
            # For testing without API key
            self.configured = False

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using rough estimation.

        Google doesn't provide a public tokenizer for all models, so we use approximation.
        Gemini uses a similar tokenizer to other models, roughly 4 chars per token.
        """
        return len(text) // 4 + 5  # Add small buffer for safety

    def _parse_prompt_json(self, prompt_json: str) -> dict[str, Any]:
        """Parse the prompt JSON and extract relevant information."""
        try:
            prompt_data = json.loads(prompt_json)
            return prompt_data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse prompt JSON: {e}")
            return {"messages": [{"role": "user", "content": prompt_json}]}

    def _convert_messages_to_google_format(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI-style messages to Google AI format.

        Google AI expects a different message format with 'parts' instead of 'content'.
        """
        google_messages = []

        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")

            # Map roles
            if role == "system":
                # Google AI doesn't have a system role, so we prepend to the first user message
                continue  # Handle system messages separately
            elif role == "assistant":
                google_role = "model"
            else:
                google_role = "user"

            # Handle content
            if isinstance(content, str):
                google_messages.append({"role": google_role, "parts": [{"text": content}]})
            elif isinstance(content, list):
                # Handle multi-modal content
                parts = []
                for item in content:
                    if item.get("type") == "text":
                        parts.append({"text": item.get("text", "")})
                    elif item.get("type") == "image_url":
                        # Handle image URLs - would need to download and convert
                        parts.append({"text": f"[Image: {item.get('image_url', {}).get('url', 'unknown')}]"})
                    elif item.get("type") == "image":
                        # Handle base64 images
                        if "source" in item and item["source"].get("type") == "base64":
                            # Convert base64 to image data
                            base64.b64decode(item["source"]["data"])
                            parts.append(
                                {
                                    "inline_data": {
                                        "mime_type": item["source"].get("media_type", "image/jpeg"),
                                        "data": item["source"]["data"],
                                    }
                                }
                            )

                if parts:
                    google_messages.append({"role": google_role, "parts": parts})

        return google_messages

    def _extract_system_prompt(self, messages: list[dict[str, Any]]) -> str:
        """Extract system prompt from messages."""
        system_parts = []
        for message in messages:
            if message.get("role") == "system":
                system_parts.append(message.get("content", ""))
        return "\n".join(system_parts) if system_parts else ""

    def _estimate_output_tokens(self, input_tokens: int, model: str) -> int:
        """Estimate output tokens based on input and model."""
        # Conservative estimates based on typical usage patterns
        if "pro" in model.lower():
            return min(input_tokens // 2, 8192)  # Pro models can be more detailed
        elif "flash" in model.lower():
            return min(input_tokens // 3, 8192)  # Flash is optimized for speed
        else:
            return min(input_tokens // 3, 4096)  # Conservative default

    def _calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> int:
        """Calculate cost in USD micros."""
        pricing = GOOGLE_PRICING.get(model, GOOGLE_PRICING[DEFAULT_MODEL])

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
                    # Handle multi-modal content
                    for item in content:
                        if item.get("type") == "text":
                            input_tokens += self._count_tokens(item.get("text", ""))
                        elif item.get("type") in ["image_url", "image"]:
                            # Vision models: rough estimate for image processing
                            input_tokens += 258  # Base cost for image analysis in Gemini

            # Add tokens for function definitions if present
            functions = prompt_data.get("functions", [])
            tools = prompt_data.get("tools", [])

            for func in functions:
                func_str = json.dumps(func)
                input_tokens += self._count_tokens(func_str)

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
                    "function_tokens": sum(self._count_tokens(json.dumps(f)) for f in functions),
                    "tool_tokens": sum(self._count_tokens(json.dumps(t)) for t in tools),
                },
            }

            # Tool cost breakdown
            tool_cost_breakdown = {
                "tools_used": [tool.get("function", {}).get("name", "unknown") for tool in tools],
                "total_tool_cost_usd_micros": 0,  # Google AI doesn't charge extra for function calls
                "function_definitions_cost": sum(self._count_tokens(json.dumps(f)) for f in functions)
                * GOOGLE_PRICING.get(model, GOOGLE_PRICING[DEFAULT_MODEL])["input"]
                // 1000,
            }

            return adapter_pb2.EstimateResponse(
                in_tokens=input_tokens,
                out_tokens=output_tokens,
                usd_micros=cost_micros,
                confidence=0.8,  # Good confidence for Google AI estimates
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
                token_estimates_json=json.dumps(
                    {"input_tokens": fallback_tokens, "output_tokens": fallback_tokens // 2}
                ),
            )

    async def Stream(self, req: adapter_pb2.StreamRequest, ctx: Any) -> AsyncIterator[adapter_pb2.StreamChunk]:  # noqa: N802
        """Stream response chunks for a given request."""
        try:
            if not self.configured:
                yield adapter_pb2.StreamChunk(
                    type="agent.result.error",
                    content_json=json.dumps(
                        {
                            "error": "Google API key not configured",
                            "adapter": "google_adapter",
                            "error_type": "ConfigurationError",
                        }
                    ),
                    confidence=0.0,
                    partial_in_tokens=0,
                    partial_out_tokens=0,
                    partial_usd_micros=0,
                    more=False,
                )
                return

            prompt_data = self._parse_prompt_json(req.prompt_json)
            model_name = prompt_data.get("model", DEFAULT_MODEL)

            # Get the model
            model = genai.GenerativeModel(model_name)

            # Convert messages to Google format
            messages = prompt_data.get("messages", [])
            google_messages = self._convert_messages_to_google_format(messages)
            system_prompt = self._extract_system_prompt(messages)

            # Prepare generation config
            generation_config = {
                "temperature": prompt_data.get("temperature", 0.7),
                "max_output_tokens": prompt_data.get("max_tokens", 8192),
            }

            # Track tokens and cost
            input_tokens = 0
            output_tokens = 0
            accumulated_content = ""

            # Count input tokens
            for message in google_messages:
                for part in message.get("parts", []):
                    if "text" in part:
                        input_tokens += self._count_tokens(part["text"])

            if system_prompt:
                input_tokens += self._count_tokens(system_prompt)

            start_time = time.time()

            # Create the prompt
            if len(google_messages) == 1 and google_messages[0]["role"] == "user":
                # Single user message - use generate_content
                prompt_parts = google_messages[0]["parts"]
                if system_prompt:
                    prompt_parts = [{"text": system_prompt}] + prompt_parts

                response = model.generate_content(prompt_parts, generation_config=generation_config, stream=True)

                async for chunk in response:
                    if chunk.text:
                        text_delta = chunk.text
                        accumulated_content += text_delta
                        output_tokens += self._count_tokens(text_delta)

                        yield adapter_pb2.StreamChunk(
                            type="agent.result.partial",
                            content_json=json.dumps(
                                {
                                    "content": text_delta,
                                    "accumulated_content": accumulated_content,
                                    "model": model_name,
                                    "adapter": "google_adapter",
                                }
                            ),
                            confidence=0.8,
                            partial_in_tokens=input_tokens,
                            partial_out_tokens=output_tokens,
                            partial_usd_micros=self._calculate_cost(input_tokens, output_tokens, model_name),
                            more=True,
                        )

                # Final chunk
                final_content = {
                    "content": accumulated_content,
                    "model": model_name,
                    "adapter": "google_adapter",
                    "finish_reason": "stop",
                    "usage": {
                        "prompt_tokens": input_tokens,
                        "completion_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                    },
                    "response_time_ms": (time.time() - start_time) * 1000,
                }

                yield adapter_pb2.StreamChunk(
                    type="agent.result.final",
                    content_json=json.dumps(final_content),
                    confidence=0.9,
                    partial_in_tokens=input_tokens,
                    partial_out_tokens=output_tokens,
                    partial_usd_micros=self._calculate_cost(input_tokens, output_tokens, model_name),
                    more=False,
                )

            else:
                # Multi-turn conversation - use chat
                chat = model.start_chat(history=google_messages[:-1] if len(google_messages) > 1 else [])

                last_message = google_messages[-1] if google_messages else {"parts": [{"text": "Hello"}]}
                response = chat.send_message(last_message["parts"], generation_config=generation_config, stream=True)

                async for chunk in response:
                    if chunk.text:
                        text_delta = chunk.text
                        accumulated_content += text_delta
                        output_tokens += self._count_tokens(text_delta)

                        yield adapter_pb2.StreamChunk(
                            type="agent.result.partial",
                            content_json=json.dumps(
                                {
                                    "content": text_delta,
                                    "accumulated_content": accumulated_content,
                                    "model": model_name,
                                    "adapter": "google_adapter",
                                }
                            ),
                            confidence=0.8,
                            partial_in_tokens=input_tokens,
                            partial_out_tokens=output_tokens,
                            partial_usd_micros=self._calculate_cost(input_tokens, output_tokens, model_name),
                            more=True,
                        )

                # Final chunk
                final_content = {
                    "content": accumulated_content,
                    "model": model_name,
                    "adapter": "google_adapter",
                    "finish_reason": "stop",
                    "usage": {
                        "prompt_tokens": input_tokens,
                        "completion_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                    },
                    "response_time_ms": (time.time() - start_time) * 1000,
                }

                yield adapter_pb2.StreamChunk(
                    type="agent.result.final",
                    content_json=json.dumps(final_content),
                    confidence=0.9,
                    partial_in_tokens=input_tokens,
                    partial_out_tokens=output_tokens,
                    partial_usd_micros=self._calculate_cost(input_tokens, output_tokens, model_name),
                    more=False,
                )

        except Exception as e:
            logger.error(f"Error in Stream: {e}")
            yield adapter_pb2.StreamChunk(
                type="agent.result.error",
                content_json=json.dumps(
                    {
                        "error": str(e),
                        "adapter": "google_adapter",
                        "error_type": type(e).__name__,
                    }
                ),
                confidence=0.0,
                partial_in_tokens=0,
                partial_out_tokens=0,
                partial_usd_micros=0,
                more=False,
            )

    async def Health(self, req: adapter_pb2.HealthRequest, ctx: Any) -> adapter_pb2.HealthResponse:  # noqa: N802
        """Check health of the Google AI adapter."""
        try:
            if not self.configured:
                return adapter_pb2.HealthResponse(p95_ms=10000.0, error_rate=1.0)

            # Test Google AI API connectivity with a minimal request
            start_time = time.time()

            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content("Hi", generation_config={"max_output_tokens": 1, "temperature": 0})

            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds

            if response and response.text:
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
        if not os.getenv("GOOGLE_API_KEY"):
            return {"ok": False, "error": "GOOGLE_API_KEY not configured"}

        return {"ok": True, "adapter": "google_adapter", "models_supported": list(GOOGLE_PRICING.keys())}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _register(server: grpc.aio.Server) -> None:
    """Register the adapter service with the gRPC server."""
    adapter_pb2_grpc.add_AdapterServiceServicer_to_server(GoogleAdapter(), server)


async def serve() -> None:
    """Start the gRPC and HTTP servers."""
    # Validate configuration
    if not os.getenv("GOOGLE_API_KEY"):
        logger.error("GOOGLE_API_KEY environment variable is required")
        return

    # Start gRPC server
    grpc_server = grpc.aio.server()
    _register(grpc_server)
    grpc_server.add_insecure_port("[::]:7070")
    await grpc_server.start()
    logger.info("gRPC Google AI Adapter listening on :7070")

    # Start HTTP server for health checks
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")  # noqa: S104
    http_server = uvicorn.Server(config)
    logger.info("HTTP Health server listening on :8080")

    # Run both servers concurrently
    await asyncio.gather(grpc_server.wait_for_termination(), http_server.serve())


if __name__ == "__main__":
    asyncio.run(serve())
