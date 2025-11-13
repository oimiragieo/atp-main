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

"""ATP llama.cpp Adapter Service.

A gRPC-based adapter service that provides llama.cpp model interactions.
This adapter connects to llama.cpp servers for optimized AI model inference with support for:
- High-performance CPU and GPU inference
- Quantized model support (GGML/GGUF formats)
- Streaming responses with low latency
- Memory-efficient inference
- Multiple model format support
- Advanced sampling parameters
"""

import asyncio
import json
import logging
import os
import time
import psutil
from collections.abc import AsyncIterator
from typing import Any, Dict, List, Optional, Protocol, Union
from dataclasses import dataclass
import aiohttp
import subprocess
import threading
from pathlib import Path

import adapter_pb2
import adapter_pb2_grpc
import grpc
import uvicorn
from fastapi import FastAPI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# llama.cpp pricing estimates (in USD micros) - very cost-effective
LLAMACPP_PRICING = {
    "llama-2-7b-q4": {"input": 50, "output": 100},
    "llama-2-7b-q8": {"input": 80, "output": 160},
    "llama-2-13b-q4": {"input": 100, "output": 200},
    "llama-2-13b-q8": {"input": 150, "output": 300},
    "llama-2-70b-q4": {"input": 400, "output": 800},
    "codellama-7b-q4": {"input": 50, "output": 100},
    "codellama-13b-q4": {"input": 100, "output": 200},
    "codellama-34b-q4": {"input": 250, "output": 500},
    "mistral-7b-q4": {"input": 40, "output": 80},
    "mixtral-8x7b-q4": {"input": 200, "output": 400},
    "vicuna-7b-q4": {"input": 50, "output": 100},
    "vicuna-13b-q4": {"input": 100, "output": 200},
    "alpaca-7b-q4": {"input": 50, "output": 100},
    "default": {"input": 75, "output": 150},
}

# Default configuration
DEFAULT_MODEL = "llama-2-7b-q4"
DEFAULT_LLAMACPP_HOST = "localhost"
DEFAULT_LLAMACPP_PORT = 8080
DEFAULT_MODEL_PATH = "/models"


@dataclass
class LlamaCppParams:
    """llama.cpp generation parameters."""
    n_predict: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.1
    repeat_last_n: int = 64
    seed: int = -1
    stop: List[str] = None
    stream: bool = True
    
    def __post_init__(self):
        if self.stop is None:
            self.stop = []


@dataclass
class ModelInfo:
    """Information about a loaded model."""
    name: str
    path: str
    size_mb: int
    quantization: str
    context_length: int
    loaded: bool = False


class LlamaCppClient:
    """Client for communicating with llama.cpp server."""
    
    def __init__(self, host: str = DEFAULT_LLAMACPP_HOST, port: int = DEFAULT_LLAMACPP_PORT):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def health_check(self) -> bool:
        """Check if llama.cpp server is healthy."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
                
            async with self.session.get(f"{self.base_url}/health") as response:
                return response.status == 200
        except Exception as e:
            logger.warning(f"llama.cpp health check failed: {e}")
            return False
    
    async def get_model_info(self) -> Dict[str, Any]:
        """Get current model information."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
                
            async with self.session.get(f"{self.base_url}/v1/models") as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("data"):
                        return data["data"][0]  # Return first model
                    return {"id": "unknown"}
                else:
                    return {"id": "unknown"}
        except Exception as e:
            logger.error(f"Error getting model info: {e}")
            return {"id": "error"}
    
    async def get_server_props(self) -> Dict[str, Any]:
        """Get server properties and capabilities."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
                
            async with self.session.get(f"{self.base_url}/props") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {}
        except Exception as e:
            logger.error(f"Error getting server props: {e}")
            return {}
    
    async def generate(
        self,
        prompt: str,
        params: LlamaCppParams = None
    ) -> str:
        """Generate text using the completion API."""
        if params is None:
            params = LlamaCppParams()
            
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            payload = {
                "prompt": prompt,
                "n_predict": params.n_predict,
                "temperature": params.temperature,
                "top_p": params.top_p,
                "top_k": params.top_k,
                "repeat_penalty": params.repeat_penalty,
                "repeat_last_n": params.repeat_last_n,
                "seed": params.seed,
                "stop": params.stop,
                "stream": False
            }
            
            async with self.session.post(
                f"{self.base_url}/completion",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("content", "")
                else:
                    error_text = await response.text()
                    raise Exception(f"llama.cpp API error {response.status}: {error_text}")
                    
        except Exception as e:
            logger.error(f"Error generating text: {e}")
            raise
    
    async def generate_stream(
        self,
        prompt: str,
        params: LlamaCppParams = None
    ) -> AsyncIterator[str]:
        """Generate text using the streaming completion API."""
        if params is None:
            params = LlamaCppParams()
            
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            payload = {
                "prompt": prompt,
                "n_predict": params.n_predict,
                "temperature": params.temperature,
                "top_p": params.top_p,
                "top_k": params.top_k,
                "repeat_penalty": params.repeat_penalty,
                "repeat_last_n": params.repeat_last_n,
                "seed": params.seed,
                "stop": params.stop,
                "stream": True
            }
            
            async with self.session.post(
                f"{self.base_url}/completion",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"llama.cpp API error {response.status}: {error_text}")
                
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        data_str = line[6:]  # Remove 'data: ' prefix
                        if data_str == '[DONE]':
                            break
                        try:
                            data = json.loads(data_str)
                            content = data.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
                            
        except Exception as e:
            logger.error(f"Error streaming text: {e}")
            raise
    
    async def tokenize(self, text: str) -> List[int]:
        """Tokenize text and return token IDs."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            payload = {"content": text}
            
            async with self.session.post(
                f"{self.base_url}/tokenize",
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("tokens", [])
                else:
                    return []
                    
        except Exception as e:
            logger.error(f"Error tokenizing text: {e}")
            return []
    
    async def detokenize(self, tokens: List[int]) -> str:
        """Detokenize token IDs back to text."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            payload = {"tokens": tokens}
            
            async with self.session.post(
                f"{self.base_url}/detokenize",
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("content", "")
                else:
                    return ""
                    
        except Exception as e:
            logger.error(f"Error detokenizing tokens: {e}")
            return ""


class ModelManager:
    """Manages llama.cpp models and server instances."""
    
    def __init__(self, model_path: str = DEFAULT_MODEL_PATH):
        self.model_path = Path(model_path)
        self.available_models = {}
        self.current_process = None
        self.current_model = None
        
    def scan_models(self) -> Dict[str, ModelInfo]:
        """Scan for available GGML/GGUF model files."""
        models = {}
        
        if not self.model_path.exists():
            logger.warning(f"Model path {self.model_path} does not exist")
            return models
        
        # Scan for GGML and GGUF files
        for pattern in ["*.ggml", "*.gguf", "*.bin"]:
            for model_file in self.model_path.glob(pattern):
                try:
                    # Extract model info from filename
                    name = model_file.stem
                    size_mb = model_file.stat().st_size // (1024 * 1024)
                    
                    # Determine quantization from filename
                    quantization = "unknown"
                    if "q4" in name.lower():
                        quantization = "Q4"
                    elif "q8" in name.lower():
                        quantization = "Q8"
                    elif "q5" in name.lower():
                        quantization = "Q5"
                    elif "f16" in name.lower():
                        quantization = "F16"
                    elif "f32" in name.lower():
                        quantization = "F32"
                    
                    # Estimate context length (default to 2048)
                    context_length = 2048
                    if "4k" in name.lower():
                        context_length = 4096
                    elif "8k" in name.lower():
                        context_length = 8192
                    elif "16k" in name.lower():
                        context_length = 16384
                    elif "32k" in name.lower():
                        context_length = 32768
                    
                    models[name] = ModelInfo(
                        name=name,
                        path=str(model_file),
                        size_mb=size_mb,
                        quantization=quantization,
                        context_length=context_length
                    )
                    
                except Exception as e:
                    logger.warning(f"Error processing model file {model_file}: {e}")
        
        self.available_models = models
        return models
    
    def start_server(
        self, 
        model_name: str, 
        port: int = DEFAULT_LLAMACPP_PORT,
        n_gpu_layers: int = 0,
        context_size: int = 2048,
        threads: int = None
    ) -> bool:
        """Start llama.cpp server with specified model."""
        if model_name not in self.available_models:
            logger.error(f"Model {model_name} not found")
            return False
        
        # Stop existing server
        self.stop_server()
        
        model_info = self.available_models[model_name]
        
        # Determine number of threads
        if threads is None:
            threads = min(psutil.cpu_count(), 8)  # Reasonable default
        
        # Build command
        cmd = [
            "llama-server",  # Assuming llama-server is in PATH
            "-m", model_info.path,
            "--port", str(port),
            "--host", "0.0.0.0",
            "-c", str(context_size),
            "-t", str(threads),
            "--log-format", "json"
        ]
        
        # Add GPU layers if specified
        if n_gpu_layers > 0:
            cmd.extend(["-ngl", str(n_gpu_layers)])
        
        try:
            # Start server process
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.current_model = model_name
            logger.info(f"Started llama.cpp server with model {model_name} on port {port}")
            
            # Wait a moment for server to start
            time.sleep(2)
            
            return self.current_process.poll() is None
            
        except Exception as e:
            logger.error(f"Error starting llama.cpp server: {e}")
            return False
    
    def stop_server(self):
        """Stop the current llama.cpp server."""
        if self.current_process:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.current_process.kill()
                self.current_process.wait()
            except Exception as e:
                logger.error(f"Error stopping server: {e}")
            finally:
                self.current_process = None
                self.current_model = None
    
    def is_server_running(self) -> bool:
        """Check if server is currently running."""
        return self.current_process is not None and self.current_process.poll() is None


class _AdapterServicerProto(Protocol):
    """Protocol for adapter servicer methods."""
    async def Estimate(self, req: adapter_pb2.EstimateRequest, ctx: Any) -> adapter_pb2.EstimateResponse: ...  # noqa: N802
    async def Stream(self, req: adapter_pb2.StreamRequest, ctx: Any) -> AsyncIterator[adapter_pb2.StreamChunk]: ...  # noqa: N802
    async def Health(self, req: adapter_pb2.HealthRequest, ctx: Any) -> adapter_pb2.HealthResponse: ...  # noqa: N802


class LlamaCppAdapter:
    """llama.cpp adapter implementation."""

    def __init__(self):
        """Initialize the llama.cpp adapter."""
        self.llamacpp_host = os.getenv("LLAMACPP_HOST", DEFAULT_LLAMACPP_HOST)
        self.llamacpp_port = int(os.getenv("LLAMACPP_PORT", DEFAULT_LLAMACPP_PORT))
        self.model_path = os.getenv("MODEL_PATH", DEFAULT_MODEL_PATH)
        
        # Initialize components
        self.llamacpp_client = LlamaCppClient(self.llamacpp_host, self.llamacpp_port)
        self.model_manager = ModelManager(self.model_path)
        
        # Scan for available models
        self.model_manager.scan_models()
        
        logger.info(f"llama.cpp adapter initialized - Host: {self.llamacpp_host}:{self.llamacpp_port}")
        logger.info(f"Found {len(self.model_manager.available_models)} models in {self.model_path}")
        
    def _parse_prompt_json(self, prompt_json: str) -> Dict[str, Any]:
        """Parse the prompt JSON and extract relevant information."""
        try:
            prompt_data = json.loads(prompt_json)
            return prompt_data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse prompt JSON: {e}")
            return {"prompt": prompt_json, "model": DEFAULT_MODEL}
    
    async def _count_tokens(self, text: str) -> int:
        """Count tokens using llama.cpp tokenizer."""
        try:
            async with self.llamacpp_client as client:
                tokens = await client.tokenize(text)
                return len(tokens)
        except Exception:
            # Fallback to estimation
            return max(1, len(text) // 4)
    
    def _calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> int:
        """Calculate cost in USD micros."""
        # Normalize model name for pricing lookup
        model_key = model.lower()
        for key in LLAMACPP_PRICING:
            if key in model_key:
                pricing = LLAMACPP_PRICING[key]
                break
        else:
            pricing = LLAMACPP_PRICING["default"]
        
        input_cost = (input_tokens * pricing["input"]) // 1000
        output_cost = (output_tokens * pricing["output"]) // 1000
        
        return input_cost + output_cost
    
    def _create_llamacpp_params(self, prompt_data: Dict[str, Any]) -> LlamaCppParams:
        """Create llama.cpp parameters from prompt data."""
        return LlamaCppParams(
            n_predict=prompt_data.get("max_tokens", 512),
            temperature=prompt_data.get("temperature", 0.7),
            top_p=prompt_data.get("top_p", 0.9),
            top_k=prompt_data.get("top_k", 40),
            repeat_penalty=prompt_data.get("repeat_penalty", 1.1),
            repeat_last_n=prompt_data.get("repeat_last_n", 64),
            seed=prompt_data.get("seed", -1),
            stop=prompt_data.get("stop", [])
        )

    async def Estimate(self, req: adapter_pb2.EstimateRequest, ctx: Any) -> adapter_pb2.EstimateResponse:  # noqa: N802
        """Estimate token usage and cost for a given prompt."""
        try:
            prompt_data = self._parse_prompt_json(req.prompt_json)
            model = prompt_data.get("model", DEFAULT_MODEL)
            prompt = prompt_data.get("prompt", "")
            max_tokens = prompt_data.get("max_tokens", 512)
            
            # Count input tokens using tokenizer if available
            input_tokens = await self._count_tokens(prompt)
            
            # Estimate output tokens (conservative)
            output_tokens = min(max_tokens, input_tokens // 2 + 50)
            
            # Calculate cost
            cost_usd_micros = self._calculate_cost(input_tokens, output_tokens, model)
            
            # Estimate latency based on model size and quantization
            base_latency_ms = 100  # Base latency for llama.cpp
            if "70b" in model.lower():
                base_latency_ms *= 4
            elif "34b" in model.lower():
                base_latency_ms *= 3
            elif "13b" in model.lower():
                base_latency_ms *= 2
            
            # Quantization affects speed
            if "q4" in model.lower():
                base_latency_ms *= 0.7  # Q4 is faster
            elif "q8" in model.lower():
                base_latency_ms *= 1.2  # Q8 is slower but higher quality
            
            # Adjust for output length
            latency_ms = int(base_latency_ms * (output_tokens / 100))
            
            return adapter_pb2.EstimateResponse(
                in_tokens=input_tokens,
                out_tokens=output_tokens,
                usd_micros=cost_usd_micros,
                p95_tokens=output_tokens,
                p95_usd_micros=cost_usd_micros,
                variance_tokens=0.1,
                variance_usd=0.1,
                confidence=0.9  # High confidence for local models
            )
            
        except Exception as e:
            logger.error(f"Error in estimate: {e}")
            return adapter_pb2.EstimateResponse(
                in_tokens=100,
                out_tokens=200,
                usd_micros=300,
                p95_tokens=200,
                p95_usd_micros=300,
                variance_tokens=0.15,
                variance_usd=0.15,
                confidence=0.5
            )

    async def Stream(self, req: adapter_pb2.StreamRequest, ctx: Any) -> AsyncIterator[adapter_pb2.StreamChunk]:  # noqa: N802
        """Stream response from llama.cpp model."""
        try:
            prompt_data = self._parse_prompt_json(req.prompt_json)
            prompt = prompt_data.get("prompt", "")
            params = self._create_llamacpp_params(prompt_data)
            
            # Use streaming API
            async with self.llamacpp_client as client:
                async for chunk in client.generate_stream(prompt, params):
                    yield adapter_pb2.StreamChunk(
                        type="text",
                        content_json=json.dumps({"text": chunk}),
                        confidence=0.9,
                        more=True
                    )
            
            # Send final chunk
            yield adapter_pb2.StreamChunk(
                type="text",
                content_json=json.dumps({"text": ""}),
                confidence=1.0,
                more=False
            )
                
        except Exception as e:
            logger.error(f"Error in stream: {e}")
            yield adapter_pb2.StreamChunk(
                type="error",
                content_json=json.dumps({"error": str(e)}),
                confidence=0.0,
                more=False
            )

    async def Health(self, req: adapter_pb2.HealthRequest, ctx: Any) -> adapter_pb2.HealthResponse:  # noqa: N802
        """Check adapter and llama.cpp server health."""
        try:
            # Check llama.cpp server health
            async with self.llamacpp_client as client:
                llamacpp_healthy = await client.health_check()
            
            # Check if model manager has server running
            server_running = self.model_manager.is_server_running()
            
            # Determine overall health
            healthy = llamacpp_healthy and server_running
            
            return adapter_pb2.HealthResponse(
                p95_ms=80.0 if healthy else 5000.0,
                error_rate=0.01 if healthy else 0.9
            )
            
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            return adapter_pb2.HealthResponse(
                p95_ms=10000.0,
                error_rate=1.0
            )


class LlamaCppAdapterServicer(adapter_pb2_grpc.AdapterServiceServicer):
    """gRPC servicer for llama.cpp adapter."""

    def __init__(self):
        self.adapter = LlamaCppAdapter()

    async def Estimate(self, request: adapter_pb2.EstimateRequest, context: grpc.aio.ServicerContext) -> adapter_pb2.EstimateResponse:  # noqa: N802
        return await self.adapter.Estimate(request, context)

    async def Stream(self, request: adapter_pb2.StreamRequest, context: grpc.aio.ServicerContext) -> AsyncIterator[adapter_pb2.StreamChunk]:  # noqa: N802
        async for chunk in self.adapter.Stream(request, context):
            yield chunk

    async def Health(self, request: adapter_pb2.HealthRequest, context: grpc.aio.ServicerContext) -> adapter_pb2.HealthResponse:  # noqa: N802
        return await self.adapter.Health(request, context)


async def serve():
    """Start the gRPC server."""
    server = grpc.aio.server()
    adapter_pb2_grpc.add_AdapterServiceServicer_to_server(LlamaCppAdapterServicer(), server)
    
    port = os.getenv("GRPC_PORT", "50051")
    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)
    
    logger.info(f"Starting llama.cpp adapter server on {listen_addr}")
    await server.start()
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down llama.cpp adapter server")
        await server.stop(grace=5)


# FastAPI app for HTTP health checks and management
app = FastAPI(
    title="ATP llama.cpp Adapter",
    description="llama.cpp adapter for ATP",
    version="1.0.0"
)

# Global adapter instance for HTTP endpoints
_adapter_instance = None


def get_adapter():
    """Get or create adapter instance."""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = LlamaCppAdapter()
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
        "error_rate": health_resp.error_rate
    }


@app.get("/models")
async def get_available_models():
    """Get available models."""
    adapter = get_adapter()
    
    models = adapter.model_manager.scan_models()
    
    return {
        "models": [
            {
                "name": info.name,
                "size_mb": info.size_mb,
                "quantization": info.quantization,
                "context_length": info.context_length,
                "loaded": info.name == adapter.model_manager.current_model
            }
            for info in models.values()
        ],
        "current_model": adapter.model_manager.current_model
    }


@app.post("/models/{model_name}/load")
async def load_model(
    model_name: str,
    n_gpu_layers: int = 0,
    context_size: int = 2048,
    threads: Optional[int] = None
):
    """Load a specific model."""
    adapter = get_adapter()
    
    try:
        success = adapter.model_manager.start_server(
            model_name=model_name,
            port=adapter.llamacpp_port,
            n_gpu_layers=n_gpu_layers,
            context_size=context_size,
            threads=threads
        )
        return {
            "success": success,
            "model": model_name,
            "port": adapter.llamacpp_port
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/models/stop")
async def stop_model():
    """Stop the current model server."""
    adapter = get_adapter()
    
    try:
        adapter.model_manager.stop_server()
        return {"success": True, "message": "Model server stopped"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/server/props")
async def get_server_props():
    """Get server properties."""
    adapter = get_adapter()
    
    try:
        async with adapter.llamacpp_client as client:
            props = await client.get_server_props()
        return props
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "http":
        # Run HTTP server for development/testing
        uvicorn.run(app, host="0.0.0.0", port=8080)
    else:
        # Run gRPC server
        asyncio.run(serve())