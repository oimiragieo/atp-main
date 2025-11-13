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

"""ATP Text Generation WebUI Adapter Service.

A gRPC-based adapter service that provides Text Generation WebUI model interactions.
This adapter connects to Text Generation WebUI servers for AI model inference with support for:
- Streaming responses with real-time generation
- Multiple model support and hot-swapping
- Advanced generation parameters
- WebSocket and HTTP API compatibility
- Model management and configuration
"""

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

import adapter_pb2
import adapter_pb2_grpc
import aiohttp
import grpc
import uvicorn
import websockets
from fastapi import FastAPI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Text Generation WebUI pricing estimates (in USD micros)
TEXTGEN_PRICING = {
    "llama-2-7b": {"input": 150, "output": 300},
    "llama-2-13b": {"input": 300, "output": 600},
    "llama-2-70b": {"input": 1500, "output": 3000},
    "codellama-7b": {"input": 150, "output": 300},
    "codellama-13b": {"input": 300, "output": 600},
    "codellama-34b": {"input": 800, "output": 1600},
    "mistral-7b": {"input": 120, "output": 240},
    "mixtral-8x7b": {"input": 500, "output": 1000},
    "vicuna-7b": {"input": 150, "output": 300},
    "vicuna-13b": {"input": 300, "output": 600},
    "alpaca-7b": {"input": 150, "output": 300},
    "wizard-7b": {"input": 150, "output": 300},
    "wizard-13b": {"input": 300, "output": 600},
    "default": {"input": 200, "output": 400},
}

# Default configuration
DEFAULT_MODEL = "llama-2-7b"
DEFAULT_TEXTGEN_HOST = "localhost"
DEFAULT_TEXTGEN_PORT = 5000
DEFAULT_TEXTGEN_WS_PORT = 5005


@dataclass
class GenerationParams:
    """Text generation parameters."""

    max_new_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    repetition_penalty: float = 1.1
    do_sample: bool = True
    seed: int = -1
    stop_strings: list[str] = None

    def __post_init__(self):
        if self.stop_strings is None:
            self.stop_strings = []


class TextGenWebUIClient:
    """Client for communicating with Text Generation WebUI server."""

    def __init__(
        self, host: str = DEFAULT_TEXTGEN_HOST, port: int = DEFAULT_TEXTGEN_PORT, ws_port: int = DEFAULT_TEXTGEN_WS_PORT
    ):
        self.host = host
        self.port = port
        self.ws_port = ws_port
        self.base_url = f"http://{host}:{port}"
        self.ws_url = f"ws://{host}:{ws_port}"
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def health_check(self) -> bool:
        """Check if Text Generation WebUI server is healthy."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(f"{self.base_url}/api/v1/model") as response:
                return response.status == 200
        except Exception as e:
            logger.warning(f"Text Generation WebUI health check failed: {e}")
            return False

    async def get_model_info(self) -> dict[str, Any]:
        """Get current model information."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(f"{self.base_url}/api/v1/model") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"result": "unknown"}
        except Exception as e:
            logger.error(f"Error getting model info: {e}")
            return {"result": "error"}

    async def get_available_models(self) -> list[str]:
        """Get list of available models."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(f"{self.base_url}/api/v1/internal/model/list") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("model_names", [])
                else:
                    return []
        except Exception as e:
            logger.error(f"Error getting available models: {e}")
            return []

    async def load_model(self, model_name: str) -> bool:
        """Load a specific model."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            payload = {"model_name": model_name}

            async with self.session.post(f"{self.base_url}/api/v1/internal/model/load", json=payload) as response:
                return response.status == 200

        except Exception as e:
            logger.error(f"Error loading model {model_name}: {e}")
            return False

    async def generate(self, prompt: str, params: GenerationParams = None) -> str:
        """Generate text using the blocking API."""
        if params is None:
            params = GenerationParams()

        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            payload = {
                "prompt": prompt,
                "max_new_tokens": params.max_new_tokens,
                "temperature": params.temperature,
                "top_p": params.top_p,
                "top_k": params.top_k,
                "repetition_penalty": params.repetition_penalty,
                "do_sample": params.do_sample,
                "seed": params.seed,
                "stop": params.stop_strings,
            }

            async with self.session.post(
                f"{self.base_url}/api/v1/generate", json=payload, timeout=aiohttp.ClientTimeout(total=300)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["results"][0]["text"]
                else:
                    error_text = await response.text()
                    raise Exception(f"Text Generation WebUI API error {response.status}: {error_text}")

        except Exception as e:
            logger.error(f"Error generating text: {e}")
            raise

    async def generate_stream(self, prompt: str, params: GenerationParams = None) -> AsyncIterator[str]:
        """Generate text using the streaming WebSocket API."""
        if params is None:
            params = GenerationParams()

        try:
            payload = {
                "prompt": prompt,
                "max_new_tokens": params.max_new_tokens,
                "temperature": params.temperature,
                "top_p": params.top_p,
                "top_k": params.top_k,
                "repetition_penalty": params.repetition_penalty,
                "do_sample": params.do_sample,
                "seed": params.seed,
                "stop": params.stop_strings,
                "stream": True,
            }

            async with websockets.connect(f"{self.ws_url}/api/v1/stream") as websocket:
                # Send generation request
                await websocket.send(json.dumps(payload))

                # Receive streaming responses
                async for message in websocket:
                    try:
                        data = json.loads(message)

                        if data.get("event") == "text_stream":
                            text = data.get("text", "")
                            if text:
                                yield text
                        elif data.get("event") == "stream_end":
                            break
                        elif data.get("event") == "error":
                            error_msg = data.get("error", "Unknown error")
                            raise Exception(f"Streaming error: {error_msg}")

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.error(f"Error streaming text: {e}")
            raise


class _AdapterServicerProto(Protocol):
    """Protocol for adapter servicer methods."""

    async def Estimate(self, req: adapter_pb2.EstimateRequest, ctx: Any) -> adapter_pb2.EstimateResponse: ...  # noqa: N802
    async def Stream(self, req: adapter_pb2.StreamRequest, ctx: Any) -> AsyncIterator[adapter_pb2.StreamChunk]: ...  # noqa: N802
    async def Health(self, req: adapter_pb2.HealthRequest, ctx: Any) -> adapter_pb2.HealthResponse: ...  # noqa: N802


class TextGenWebUIAdapter:
    """Text Generation WebUI adapter implementation."""

    def __init__(self):
        """Initialize the Text Generation WebUI adapter."""
        self.textgen_host = os.getenv("TEXTGEN_HOST", DEFAULT_TEXTGEN_HOST)
        self.textgen_port = int(os.getenv("TEXTGEN_PORT", DEFAULT_TEXTGEN_PORT))
        self.textgen_ws_port = int(os.getenv("TEXTGEN_WS_PORT", DEFAULT_TEXTGEN_WS_PORT))

        # Initialize client
        self.textgen_client = TextGenWebUIClient(self.textgen_host, self.textgen_port, self.textgen_ws_port)

        logger.info(f"Text Generation WebUI adapter initialized - Host: {self.textgen_host}:{self.textgen_port}")

    def _parse_prompt_json(self, prompt_json: str) -> dict[str, Any]:
        """Parse the prompt JSON and extract relevant information."""
        try:
            prompt_data = json.loads(prompt_json)
            return prompt_data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse prompt JSON: {e}")
            return {"prompt": prompt_json, "model": DEFAULT_MODEL}

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation)."""
        # Simple estimation: ~4 characters per token
        return max(1, len(text) // 4)

    def _calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> int:
        """Calculate cost in USD micros."""
        # Normalize model name for pricing lookup
        model_key = model.lower()
        for key in TEXTGEN_PRICING:
            if key in model_key:
                pricing = TEXTGEN_PRICING[key]
                break
        else:
            pricing = TEXTGEN_PRICING["default"]

        input_cost = (input_tokens * pricing["input"]) // 1000
        output_cost = (output_tokens * pricing["output"]) // 1000

        return input_cost + output_cost

    def _create_generation_params(self, prompt_data: dict[str, Any]) -> GenerationParams:
        """Create generation parameters from prompt data."""
        return GenerationParams(
            max_new_tokens=prompt_data.get("max_tokens", 512),
            temperature=prompt_data.get("temperature", 0.7),
            top_p=prompt_data.get("top_p", 0.9),
            top_k=prompt_data.get("top_k", 40),
            repetition_penalty=prompt_data.get("repetition_penalty", 1.1),
            do_sample=prompt_data.get("do_sample", True),
            seed=prompt_data.get("seed", -1),
            stop_strings=prompt_data.get("stop", []),
        )

    async def Estimate(self, req: adapter_pb2.EstimateRequest, ctx: Any) -> adapter_pb2.EstimateResponse:  # noqa: N802
        """Estimate token usage and cost for a given prompt."""
        try:
            prompt_data = self._parse_prompt_json(req.prompt_json)
            model = prompt_data.get("model", DEFAULT_MODEL)
            prompt = prompt_data.get("prompt", "")
            max_tokens = prompt_data.get("max_tokens", 512)

            # Estimate input tokens
            input_tokens = self._estimate_tokens(prompt)

            # Estimate output tokens (conservative)
            output_tokens = min(max_tokens, input_tokens // 2 + 100)

            # Calculate cost
            cost_usd_micros = self._calculate_cost(input_tokens, output_tokens, model)

            # Estimate latency based on model complexity
            base_latency_ms = 200  # Base latency for text generation
            if "70b" in model.lower():
                base_latency_ms *= 3
            elif "13b" in model.lower():
                base_latency_ms *= 2

            # Adjust for output length
            int(base_latency_ms * (output_tokens / 100))

            return adapter_pb2.EstimateResponse(
                in_tokens=input_tokens,
                out_tokens=output_tokens,
                usd_micros=cost_usd_micros,
                p95_tokens=output_tokens,
                p95_usd_micros=cost_usd_micros,
                variance_tokens=0.15,
                variance_usd=0.15,
                confidence=0.75,
            )

        except Exception as e:
            logger.error(f"Error in estimate: {e}")
            return adapter_pb2.EstimateResponse(
                in_tokens=100,
                out_tokens=200,
                usd_micros=800,
                p95_tokens=200,
                p95_usd_micros=800,
                variance_tokens=0.2,
                variance_usd=0.2,
                confidence=0.5,
            )

    async def Stream(self, req: adapter_pb2.StreamRequest, ctx: Any) -> AsyncIterator[adapter_pb2.StreamChunk]:  # noqa: N802
        """Stream response from Text Generation WebUI model."""
        try:
            prompt_data = self._parse_prompt_json(req.prompt_json)
            prompt = prompt_data.get("prompt", "")
            params = self._create_generation_params(prompt_data)

            # Use streaming API
            async with self.textgen_client as client:
                async for chunk in client.generate_stream(prompt, params):
                    yield adapter_pb2.StreamChunk(
                        type="text", content_json=json.dumps({"text": chunk}), confidence=0.85, more=True
                    )

            # Send final chunk
            yield adapter_pb2.StreamChunk(
                type="text", content_json=json.dumps({"text": ""}), confidence=1.0, more=False
            )

        except Exception as e:
            logger.error(f"Error in stream: {e}")
            yield adapter_pb2.StreamChunk(
                type="error", content_json=json.dumps({"error": str(e)}), confidence=0.0, more=False
            )

    async def Health(self, req: adapter_pb2.HealthRequest, ctx: Any) -> adapter_pb2.HealthResponse:  # noqa: N802
        """Check adapter and Text Generation WebUI server health."""
        try:
            # Check Text Generation WebUI server health
            async with self.textgen_client as client:
                textgen_healthy = await client.health_check()

            # Determine overall health
            healthy = textgen_healthy

            return adapter_pb2.HealthResponse(p95_ms=150.0 if healthy else 5000.0, error_rate=0.02 if healthy else 0.8)

        except Exception as e:
            logger.error(f"Error in health check: {e}")
            return adapter_pb2.HealthResponse(p95_ms=10000.0, error_rate=1.0)


class TextGenWebUIAdapterServicer(adapter_pb2_grpc.AdapterServiceServicer):
    """gRPC servicer for Text Generation WebUI adapter."""

    def __init__(self):
        self.adapter = TextGenWebUIAdapter()

    async def Estimate(
        self, request: adapter_pb2.EstimateRequest, context: grpc.aio.ServicerContext
    ) -> adapter_pb2.EstimateResponse:  # noqa: N802
        return await self.adapter.Estimate(request, context)

    async def Stream(
        self, request: adapter_pb2.StreamRequest, context: grpc.aio.ServicerContext
    ) -> AsyncIterator[adapter_pb2.StreamChunk]:  # noqa: N802
        async for chunk in self.adapter.Stream(request, context):
            yield chunk

    async def Health(
        self, request: adapter_pb2.HealthRequest, context: grpc.aio.ServicerContext
    ) -> adapter_pb2.HealthResponse:  # noqa: N802
        return await self.adapter.Health(request, context)


async def serve():
    """Start the gRPC server."""
    server = grpc.aio.server()
    adapter_pb2_grpc.add_AdapterServiceServicer_to_server(TextGenWebUIAdapterServicer(), server)

    port = os.getenv("GRPC_PORT", "50051")
    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)

    logger.info(f"Starting Text Generation WebUI adapter server on {listen_addr}")
    await server.start()

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down Text Generation WebUI adapter server")
        await server.stop(grace=5)


# FastAPI app for HTTP health checks and management
app = FastAPI(
    title="ATP Text Generation WebUI Adapter", description="Text Generation WebUI adapter for ATP", version="1.0.0"
)

# Global adapter instance for HTTP endpoints
_adapter_instance = None


def get_adapter():
    """Get or create adapter instance."""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = TextGenWebUIAdapter()
    return _adapter_instance


@app.get("/health")
async def health_check():
    """HTTP health check endpoint."""
    adapter = get_adapter()

    # Create a mock health request
    health_req = adapter_pb2.HealthRequest()
    health_resp = await adapter.Health(health_req, None)

    return {
        "healthy": health_resp.error_rate < 0.1,
        "p95_latency_ms": health_resp.p95_ms,
        "error_rate": health_resp.error_rate,
    }


@app.get("/models")
async def get_available_models():
    """Get available models from Text Generation WebUI server."""
    adapter = get_adapter()

    try:
        async with adapter.textgen_client as client:
            models = await client.get_available_models()
            current_model = await client.get_model_info()
        return {"models": models, "current_model": current_model.get("result", "unknown")}
    except Exception as e:
        return {"error": str(e), "models": []}


@app.post("/models/{model_name}/load")
async def load_model(model_name: str):
    """Load a specific model."""
    adapter = get_adapter()

    try:
        async with adapter.textgen_client as client:
            success = await client.load_model(model_name)
        return {"success": success, "model": model_name}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "http":
        # Run HTTP server for development/testing
        uvicorn.run(app, host="0.0.0.0", port=8080)
    else:
        # Run gRPC server
        asyncio.run(serve())
