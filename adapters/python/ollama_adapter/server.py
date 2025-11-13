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

"""ATP Ollama Adapter Service.

A gRPC-based adapter service that provides Ollama model interactions.
This adapter connects to Ollama servers for AI model inference.

The service implements the standard adapter protocol defined in adapter.proto,
providing estimation, streaming, and health check capabilities.
"""

import asyncio
import json
import random
from collections.abc import AsyncIterator
from typing import Any, Protocol

import adapter_pb2
import adapter_pb2_grpc
import grpc
import uvicorn
from fastapi import FastAPI


class _AdapterServicerProto(Protocol):
    """Protocol for adapter servicer methods."""
    async def Estimate(self, req: adapter_pb2.EstimateRequest, ctx: Any) -> adapter_pb2.EstimateResponse: ...  # noqa: N802
    async def Stream(self, req: adapter_pb2.StreamRequest, ctx: Any) -> AsyncIterator[adapter_pb2.StreamChunk]: ...  # noqa: N802
    async def Health(self, req: adapter_pb2.HealthRequest, ctx: Any) -> adapter_pb2.HealthResponse: ...  # noqa: N802


class Adapter:
    """Ollama adapter implementation providing AI model interactions via Ollama."""

    async def Estimate(self, req: adapter_pb2.EstimateRequest, ctx: Any) -> adapter_pb2.EstimateResponse:  # noqa: N802 gRPC method name defined by proto
        """Estimate token usage and cost for a given prompt.

        Args:
            req: The estimate request containing the prompt
            ctx: gRPC context

        Returns:
            EstimateResponse with token counts and cost estimates
        """
        tok = len(req.prompt_json.encode()) // 4 + 200
        out = max(50, tok // 8)

        # Basic token estimates breakdown
        token_estimates = {
            "input_tokens": tok,
            "output_tokens": out,
            "total_tokens": tok + out,
            "breakdown": {"prompt_tokens": tok, "completion_tokens": out},
        }

        # Tool cost breakdown (empty for now, can be extended)
        tool_cost_breakdown = {"tools_used": [], "total_tool_cost_usd_micros": 0}

        return adapter_pb2.EstimateResponse(
            in_tokens=tok,
            out_tokens=out,
            usd_micros=0,
            confidence=0.7,
            tool_cost_breakdown_json=json.dumps(tool_cost_breakdown),
            token_estimates_json=json.dumps(token_estimates),
        )

    async def Stream(self, req: adapter_pb2.StreamRequest, ctx: Any) -> AsyncIterator[adapter_pb2.StreamChunk]:  # noqa: N802
        """Stream response chunks for a given request.

        Args:
            req: The stream request
            ctx: gRPC context

        Yields:
            StreamChunk objects with partial responses
        """
        for i in range(3):
            await asyncio.sleep(0.15 + random.random() * 0.05)
            yield adapter_pb2.StreamChunk(
                type="agent.result.partial",
                content_json=json.dumps({"chunk": i, "adapter": "ollama_adapter"}),
                confidence=0.6,
                partial_in_tokens=200,
                partial_out_tokens=50,
                partial_usd_micros=0,
                more=True,
            )
        yield adapter_pb2.StreamChunk(
            type="agent.result.final",
            content_json=json.dumps({"ok": True, "adapter": "ollama_adapter"}),
            confidence=0.8,
            partial_in_tokens=100,
            partial_out_tokens=60,
            partial_usd_micros=0,
            more=False,
        )

    async def Health(self, req: adapter_pb2.HealthRequest, ctx: Any) -> adapter_pb2.HealthResponse:  # noqa: N802
        return adapter_pb2.HealthResponse(p95_ms=900.0, error_rate=0.01)


# HTTP health endpoint
app = FastAPI()


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


def _register(server: grpc.aio.Server) -> None:
    adapter_pb2_grpc.add_AdapterServiceServicer_to_server(Adapter(), server)


async def serve() -> None:
    # Start gRPC server
    grpc_server = grpc.aio.server()
    _register(grpc_server)
    grpc_server.add_insecure_port("[::]:7070")
    await grpc_server.start()
    print("gRPC Adapter listening on :7070")

    # Start HTTP server for health checks
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")  # noqa: S104
    http_server = uvicorn.Server(config)
    print("HTTP Health server listening on :8080")

    # Run both servers concurrently
    await asyncio.gather(
        grpc_server.wait_for_termination(),
        http_server.serve()
    )


if __name__ == "__main__":
    asyncio.run(serve())
