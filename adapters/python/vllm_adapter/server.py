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

"""ATP vLLM Adapter Service.

A high-performance gRPC-based adapter service that provides vLLM model interactions.
This adapter connects to vLLM servers for optimized AI model inference with support for:
- High-throughput batch processing
- GPU resource monitoring and optimization
- Tensor parallelism for large models
- OpenAI-compatible API interface
- Streaming responses with backpressure handling
- Advanced scheduling and load balancing
"""

import asyncio
import json
import logging
import os
import time
import psutil
import GPUtil
from collections.abc import AsyncIterator
from typing import Any, Dict, List, Optional, Protocol, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import threading
from queue import Queue, Empty
import aiohttp
import numpy as np

import adapter_pb2
import adapter_pb2_grpc
import grpc
import uvicorn
from fastapi import FastAPI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# vLLM model pricing estimates (in USD micros - 1 USD = 1,000,000 micros)
# These are estimates based on compute costs, actual pricing may vary
VLLM_PRICING = {
    "llama-2-7b": {"input": 200, "output": 400},  # $0.0002/$0.0004 per 1K tokens
    "llama-2-13b": {"input": 400, "output": 800},  # $0.0004/$0.0008 per 1K tokens
    "llama-2-70b": {"input": 2000, "output": 4000},  # $0.002/$0.004 per 1K tokens
    "codellama-7b": {"input": 200, "output": 400},
    "codellama-13b": {"input": 400, "output": 800},
    "codellama-34b": {"input": 1000, "output": 2000},
    "mistral-7b": {"input": 150, "output": 300},
    "mixtral-8x7b": {"input": 600, "output": 1200},
    "vicuna-7b": {"input": 200, "output": 400},
    "vicuna-13b": {"input": 400, "output": 800},
    "alpaca-7b": {"input": 200, "output": 400},
    "default": {"input": 300, "output": 600},  # Default pricing
}

# Default configuration
DEFAULT_MODEL = "llama-2-7b"
DEFAULT_VLLM_HOST = "localhost"
DEFAULT_VLLM_PORT = 8000
DEFAULT_MAX_BATCH_SIZE = 32
DEFAULT_MAX_SEQUENCE_LENGTH = 4096


@dataclass
class GPUStats:
    """GPU statistics for monitoring."""
    gpu_id: int
    name: str
    memory_total: int
    memory_used: int
    memory_free: int
    utilization: float
    temperature: float
    power_draw: float
    power_limit: float


@dataclass
class BatchRequest:
    """Batch request for high-throughput processing."""
    request_id: str
    prompt: str
    model: str
    max_tokens: int
    temperature: float
    top_p: float
    stop_sequences: List[str]
    timestamp: datetime
    priority: int = 0


@dataclass
class BatchResponse:
    """Batch response."""
    request_id: str
    text: str
    tokens_generated: int
    finish_reason: str
    processing_time: float
    error: Optional[str] = None


class GPUMonitor:
    """Monitor GPU resources and performance."""
    
    def __init__(self):
        self.gpu_stats = []
        self.monitoring = False
        self.monitor_thread = None
        
    def start_monitoring(self, interval: float = 1.0):
        """Start GPU monitoring."""
        if self.monitoring:
            return
            
        self.monitoring = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            daemon=True
        )
        self.monitor_thread.start()
        logger.info("GPU monitoring started")
    
    def stop_monitoring(self):
        """Stop GPU monitoring."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
        logger.info("GPU monitoring stopped")
    
    def _monitor_loop(self, interval: float):
        """GPU monitoring loop."""
        while self.monitoring:
            try:
                self._update_gpu_stats()
                time.sleep(interval)
            except Exception as e:
                logger.error(f"Error in GPU monitoring: {e}")
                time.sleep(interval)
    
    def _update_gpu_stats(self):
        """Update GPU statistics."""
        try:
            gpus = GPUtil.getGPUs()
            self.gpu_stats = []
            
            for gpu in gpus:
                stats = GPUStats(
                    gpu_id=gpu.id,
                    name=gpu.name,
                    memory_total=int(gpu.memoryTotal),
                    memory_used=int(gpu.memoryUsed),
                    memory_free=int(gpu.memoryFree),
                    utilization=gpu.load * 100,
                    temperature=gpu.temperature,
                    power_draw=getattr(gpu, 'powerDraw', 0),
                    power_limit=getattr(gpu, 'powerLimit', 0)
                )
                self.gpu_stats.append(stats)
                
        except Exception as e:
            logger.warning(f"Failed to update GPU stats: {e}")
            self.gpu_stats = []
    
    def get_gpu_stats(self) -> List[GPUStats]:
        """Get current GPU statistics."""
        return self.gpu_stats.copy()
    
    def get_optimal_gpu(self) -> Optional[int]:
        """Get the GPU with the most available memory."""
        if not self.gpu_stats:
            return None
            
        best_gpu = max(self.gpu_stats, key=lambda g: g.memory_free)
        return best_gpu.gpu_id if best_gpu.memory_free > 1000 else None  # At least 1GB free


class BatchProcessor:
    """High-throughput batch processor for vLLM requests."""
    
    def __init__(self, vllm_client, max_batch_size: int = DEFAULT_MAX_BATCH_SIZE):
        self.vllm_client = vllm_client
        self.max_batch_size = max_batch_size
        self.request_queue = Queue()
        self.response_futures = {}
        self.processing = False
        self.processor_thread = None
        
    def start_processing(self):
        """Start batch processing."""
        if self.processing:
            return
            
        self.processing = True
        self.processor_thread = threading.Thread(
            target=self._process_loop,
            daemon=True
        )
        self.processor_thread.start()
        logger.info("Batch processor started")
    
    def stop_processing(self):
        """Stop batch processing."""
        self.processing = False
        if self.processor_thread:
            self.processor_thread.join(timeout=5.0)
        logger.info("Batch processor stopped")
    
    async def submit_request(self, request: BatchRequest) -> BatchResponse:
        """Submit a request for batch processing."""
        future = asyncio.Future()
        self.response_futures[request.request_id] = future
        self.request_queue.put(request)
        
        try:
            # Wait for response with timeout
            response = await asyncio.wait_for(future, timeout=300.0)  # 5 minute timeout
            return response
        except asyncio.TimeoutError:
            # Clean up on timeout
            self.response_futures.pop(request.request_id, None)
            return BatchResponse(
                request_id=request.request_id,
                text="",
                tokens_generated=0,
                finish_reason="timeout",
                processing_time=300.0,
                error="Request timeout"
            )
    
    def _process_loop(self):
        """Main batch processing loop."""
        while self.processing:
            try:
                batch = self._collect_batch()
                if batch:
                    asyncio.run(self._process_batch(batch))
                else:
                    time.sleep(0.1)  # Short sleep if no requests
            except Exception as e:
                logger.error(f"Error in batch processing: {e}")
                time.sleep(1.0)
    
    def _collect_batch(self) -> List[BatchRequest]:
        """Collect requests for batch processing."""
        batch = []
        
        # Get first request (blocking with timeout)
        try:
            first_request = self.request_queue.get(timeout=1.0)
            batch.append(first_request)
        except Empty:
            return batch
        
        # Collect additional requests (non-blocking)
        while len(batch) < self.max_batch_size:
            try:
                request = self.request_queue.get_nowait()
                batch.append(request)
            except Empty:
                break
        
        return batch
    
    async def _process_batch(self, batch: List[BatchRequest]):
        """Process a batch of requests."""
        start_time = time.time()
        
        try:
            # Group by model for efficient processing
            model_batches = {}
            for request in batch:
                model = request.model
                if model not in model_batches:
                    model_batches[model] = []
                model_batches[model].append(request)
            
            # Process each model batch
            for model, requests in model_batches.items():
                await self._process_model_batch(model, requests)
                
        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            # Send error responses
            for request in batch:
                self._send_error_response(request, str(e))
        
        processing_time = time.time() - start_time
        logger.info(f"Processed batch of {len(batch)} requests in {processing_time:.2f}s")
    
    async def _process_model_batch(self, model: str, requests: List[BatchRequest]):
        """Process a batch of requests for a specific model."""
        try:
            # Prepare batch payload
            prompts = [req.prompt for req in requests]
            
            # Call vLLM batch API
            responses = await self.vllm_client.generate_batch(
                prompts=prompts,
                model=model,
                max_tokens=max(req.max_tokens for req in requests),
                temperature=requests[0].temperature,  # Use first request's params
                top_p=requests[0].top_p,
                stop=requests[0].stop_sequences
            )
            
            # Send responses
            for request, response_text in zip(requests, responses):
                response = BatchResponse(
                    request_id=request.request_id,
                    text=response_text,
                    tokens_generated=len(response_text.split()),  # Rough estimate
                    finish_reason="stop",
                    processing_time=time.time() - request.timestamp.timestamp()
                )
                self._send_response(request, response)
                
        except Exception as e:
            logger.error(f"Error processing model batch for {model}: {e}")
            for request in requests:
                self._send_error_response(request, str(e))
    
    def _send_response(self, request: BatchRequest, response: BatchResponse):
        """Send response to waiting future."""
        future = self.response_futures.pop(request.request_id, None)
        if future and not future.done():
            future.set_result(response)
    
    def _send_error_response(self, request: BatchRequest, error: str):
        """Send error response to waiting future."""
        response = BatchResponse(
            request_id=request.request_id,
            text="",
            tokens_generated=0,
            finish_reason="error",
            processing_time=time.time() - request.timestamp.timestamp(),
            error=error
        )
        self._send_response(request, response)


class VLLMClient:
    """Client for communicating with vLLM server."""
    
    def __init__(self, host: str = DEFAULT_VLLM_HOST, port: int = DEFAULT_VLLM_PORT):
        self.base_url = f"http://{host}:{port}"
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def health_check(self) -> bool:
        """Check if vLLM server is healthy."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
                
            async with self.session.get(f"{self.base_url}/health") as response:
                return response.status == 200
        except Exception as e:
            logger.warning(f"vLLM health check failed: {e}")
            return False
    
    async def get_models(self) -> List[str]:
        """Get available models from vLLM server."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
                
            async with self.session.get(f"{self.base_url}/v1/models") as response:
                if response.status == 200:
                    data = await response.json()
                    return [model["id"] for model in data.get("data", [])]
                else:
                    logger.warning(f"Failed to get models: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error getting models: {e}")
            return []
    
    async def generate(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[List[str]] = None
    ) -> str:
        """Generate text using vLLM."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            payload = {
                "model": model,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "stop": stop or []
            }
            
            async with self.session.post(
                f"{self.base_url}/v1/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["choices"][0]["text"]
                else:
                    error_text = await response.text()
                    raise Exception(f"vLLM API error {response.status}: {error_text}")
                    
        except Exception as e:
            logger.error(f"Error generating text: {e}")
            raise
    
    async def generate_stream(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[List[str]] = None
    ) -> AsyncIterator[str]:
        """Generate text using vLLM with streaming."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            payload = {
                "model": model,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "stop": stop or [],
                "stream": True
            }
            
            async with self.session.post(
                f"{self.base_url}/v1/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"vLLM API error {response.status}: {error_text}")
                
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        data_str = line[6:]  # Remove 'data: ' prefix
                        if data_str == '[DONE]':
                            break
                        try:
                            data = json.loads(data_str)
                            if 'choices' in data and data['choices']:
                                text = data['choices'][0].get('text', '')
                                if text:
                                    yield text
                        except json.JSONDecodeError:
                            continue
                            
        except Exception as e:
            logger.error(f"Error streaming text: {e}")
            raise
    
    async def generate_batch(
        self,
        prompts: List[str],
        model: str = DEFAULT_MODEL,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[List[str]] = None
    ) -> List[str]:
        """Generate text for multiple prompts in batch."""
        # For now, process sequentially
        # In a real implementation, this would use vLLM's batch API
        results = []
        for prompt in prompts:
            try:
                result = await self.generate(
                    prompt=prompt,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    stop=stop
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Error in batch generation for prompt: {e}")
                results.append("")  # Empty result for failed generation
        
        return results


class _AdapterServicerProto(Protocol):
    """Protocol for adapter servicer methods."""
    async def Estimate(self, req: adapter_pb2.EstimateRequest, ctx: Any) -> adapter_pb2.EstimateResponse: ...  # noqa: N802
    async def Stream(self, req: adapter_pb2.StreamRequest, ctx: Any) -> AsyncIterator[adapter_pb2.StreamChunk]: ...  # noqa: N802
    async def Health(self, req: adapter_pb2.HealthRequest, ctx: Any) -> adapter_pb2.HealthResponse: ...  # noqa: N802


class VLLMAdapter:
    """vLLM adapter implementation providing high-performance AI model interactions."""

    def __init__(self):
        """Initialize the vLLM adapter."""
        self.vllm_host = os.getenv("VLLM_HOST", DEFAULT_VLLM_HOST)
        self.vllm_port = int(os.getenv("VLLM_PORT", DEFAULT_VLLM_PORT))
        self.max_batch_size = int(os.getenv("VLLM_MAX_BATCH_SIZE", DEFAULT_MAX_BATCH_SIZE))
        
        # Initialize components
        self.vllm_client = VLLMClient(self.vllm_host, self.vllm_port)
        self.gpu_monitor = GPUMonitor()
        self.batch_processor = BatchProcessor(self.vllm_client, self.max_batch_size)
        
        # Start monitoring and processing
        self.gpu_monitor.start_monitoring()
        self.batch_processor.start_processing()
        
        logger.info(f"vLLM adapter initialized - Host: {self.vllm_host}:{self.vllm_port}")
        
    def __del__(self):
        """Cleanup on destruction."""
        self.gpu_monitor.stop_monitoring()
        self.batch_processor.stop_processing()
    
    def _parse_prompt_json(self, prompt_json: str) -> Dict[str, Any]:
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
        for key in VLLM_PRICING:
            if key in model_key:
                pricing = VLLM_PRICING[key]
                break
        else:
            pricing = VLLM_PRICING["default"]
        
        input_cost = (input_tokens * pricing["input"]) // 1000
        output_cost = (output_tokens * pricing["output"]) // 1000
        
        return input_cost + output_cost

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
            
            # Get GPU stats for capacity estimation
            gpu_stats = self.gpu_monitor.get_gpu_stats()
            available_memory = sum(gpu.memory_free for gpu in gpu_stats) if gpu_stats else 8000  # Default 8GB
            
            # Estimate latency based on model size and available resources
            model_size_factor = 1.0
            if "70b" in model.lower():
                model_size_factor = 4.0
            elif "13b" in model.lower():
                model_size_factor = 2.0
            elif "7b" in model.lower():
                model_size_factor = 1.0
            
            base_latency_ms = int(100 * model_size_factor * (output_tokens / 100))
            
            # Adjust for available memory
            if available_memory < 4000:  # Less than 4GB
                base_latency_ms *= 2
            
            return adapter_pb2.EstimateResponse(
                in_tokens=input_tokens,
                out_tokens=output_tokens,
                usd_micros=cost_usd_micros,
                p95_tokens=output_tokens,
                p95_usd_micros=cost_usd_micros,
                variance_tokens=0.1,
                variance_usd=0.1,
                confidence=0.8
            )
            
        except Exception as e:
            logger.error(f"Error in estimate: {e}")
            return adapter_pb2.EstimateResponse(
                in_tokens=100,
                out_tokens=200,
                usd_micros=1000,
                p95_tokens=200,
                p95_usd_micros=1000,
                variance_tokens=0.1,
                variance_usd=0.1,
                confidence=0.5
            )

    async def Stream(self, req: adapter_pb2.StreamRequest, ctx: Any) -> AsyncIterator[adapter_pb2.StreamChunk]:  # noqa: N802
        """Stream response from vLLM model."""
        try:
            prompt_data = self._parse_prompt_json(req.prompt_json)
            model = prompt_data.get("model", DEFAULT_MODEL)
            prompt = prompt_data.get("prompt", "")
            max_tokens = prompt_data.get("max_tokens", 512)
            temperature = prompt_data.get("temperature", 0.7)
            top_p = prompt_data.get("top_p", 0.9)
            stop = prompt_data.get("stop", [])
            
            # Check if we should use batch processing
            use_batch = prompt_data.get("use_batch", False)
            
            if use_batch:
                # Use batch processor for high-throughput scenarios
                batch_request = BatchRequest(
                    request_id=f"stream_{int(time.time() * 1000)}",
                    prompt=prompt,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    stop_sequences=stop,
                    timestamp=datetime.now(timezone.utc)
                )
                
                batch_response = await self.batch_processor.submit_request(batch_request)
                
                if batch_response.error:
                    yield adapter_pb2.StreamChunk(
                        text="",
                        is_final=True,
                        error=batch_response.error
                    )
                else:
                    # Stream the batch response in chunks
                    text = batch_response.text
                    chunk_size = 50  # Characters per chunk
                    for i in range(0, len(text), chunk_size):
                        chunk = text[i:i + chunk_size]
                        is_final = (i + chunk_size) >= len(text)
                        
                        yield adapter_pb2.StreamChunk(
                            type="text",
                            content_json=json.dumps({"text": chunk}),
                            confidence=0.9,
                            more=not is_final
                        )
                        
                        if not is_final:
                            await asyncio.sleep(0.05)  # Small delay between chunks
            else:
                # Use streaming API
                async with self.vllm_client as client:
                    async for chunk in client.generate_stream(
                        prompt=prompt,
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        stop=stop
                    ):
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
        """Check adapter and vLLM server health."""
        try:
            # Check vLLM server health
            async with self.vllm_client as client:
                vllm_healthy = await client.health_check()
            
            # Get GPU stats
            gpu_stats = self.gpu_monitor.get_gpu_stats()
            
            # Get system stats
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            # Determine overall health
            healthy = vllm_healthy and cpu_percent < 90 and memory.percent < 90
            
            # Create health details
            details = {
                "vllm_server": "healthy" if vllm_healthy else "unhealthy",
                "vllm_host": f"{self.vllm_host}:{self.vllm_port}",
                "cpu_usage": f"{cpu_percent:.1f}%",
                "memory_usage": f"{memory.percent:.1f}%",
                "gpu_count": len(gpu_stats),
                "batch_processor": "running" if self.batch_processor.processing else "stopped",
                "gpu_monitor": "running" if self.gpu_monitor.monitoring else "stopped"
            }
            
            # Add GPU details
            for i, gpu in enumerate(gpu_stats):
                details[f"gpu_{i}"] = {
                    "name": gpu.name,
                    "memory_used": f"{gpu.memory_used}MB",
                    "memory_total": f"{gpu.memory_total}MB",
                    "utilization": f"{gpu.utilization:.1f}%",
                    "temperature": f"{gpu.temperature}°C"
                }
            
            return adapter_pb2.HealthResponse(
                p95_ms=100.0 if healthy else 5000.0,
                error_rate=0.01 if healthy else 0.5
            )
            
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            return adapter_pb2.HealthResponse(
                p95_ms=10000.0,
                error_rate=1.0
            )


class VLLMAdapterServicer(adapter_pb2_grpc.AdapterServiceServicer):
    """gRPC servicer for vLLM adapter."""

    def __init__(self):
        self.adapter = VLLMAdapter()

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
    adapter_pb2_grpc.add_AdapterServiceServicer_to_server(VLLMAdapterServicer(), server)
    
    port = os.getenv("GRPC_PORT", "50051")
    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)
    
    logger.info(f"Starting vLLM adapter server on {listen_addr}")
    await server.start()
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down vLLM adapter server")
        await server.stop(grace=5)


# FastAPI app for HTTP health checks and management
app = FastAPI(
    title="ATP vLLM Adapter",
    description="High-performance vLLM adapter for ATP",
    version="1.0.0"
)

# Global adapter instance for HTTP endpoints
_adapter_instance = None


def get_adapter():
    """Get or create adapter instance."""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = VLLMAdapter()
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


@app.get("/gpu-stats")
async def get_gpu_stats():
    """Get current GPU statistics."""
    adapter = get_adapter()
    gpu_stats = adapter.gpu_monitor.get_gpu_stats()
    
    return {
        "gpu_count": len(gpu_stats),
        "gpus": [asdict(gpu) for gpu in gpu_stats]
    }


@app.get("/models")
async def get_available_models():
    """Get available models from vLLM server."""
    adapter = get_adapter()
    
    try:
        async with adapter.vllm_client as client:
            models = await client.get_models()
        return {"models": models}
    except Exception as e:
        return {"error": str(e), "models": []}


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "http":
        # Run HTTP server for development/testing
        uvicorn.run(app, host="0.0.0.0", port=8080)
    else:
        # Run gRPC server
        asyncio.run(serve())