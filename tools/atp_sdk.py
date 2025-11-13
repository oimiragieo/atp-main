#!/usr/bin/env python3
"""GAP-120: Python SDK Extension

Enhanced Python SDK for ATP Router with frame builders, WebSocket client,
automatic retries, and connection management.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urljoin

import aiohttp
import websockets

from router_service.frame import Frame, Lane, LaneSequencer, Meta, Payload, Window

logger = logging.getLogger(__name__)


@dataclass
class SDKConfig:
    """Configuration for ATP Python SDK."""
    base_url: str = "http://localhost:8000"
    ws_url: str = "ws://localhost:8000"
    api_key: Optional[str] = None
    tenant_id: Optional[str] = None
    session_id: Optional[str] = None
    default_timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    heartbeat_interval: float = 30.0


class ATPClientError(Exception):
    """Base exception for ATP client errors."""
    pass


class ATPConnectionError(ATPClientError):
    """Connection-related errors."""
    pass


class AuthenticationError(ATPClientError):
    """Authentication-related errors."""
    pass


class ValidationError(ATPClientError):
    """Request validation errors."""
    pass


@dataclass
class CompletionRequest:
    """Request for text completion."""
    prompt: str
    max_tokens: int = 512
    quality: str = "balanced"  # "fast", "balanced", "high"
    latency_slo_ms: int = 5000
    temperature: float = 0.7
    stream: bool = True
    tenant: Optional[str] = None
    conversation_id: Optional[str] = None
    consistency_level: str = "EVENTUAL"


@dataclass
class CompletionResponse:
    """Response from completion request."""
    text: str
    model_used: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    quality_score: float
    finished: bool = True
    error: Optional[str] = None


class FrameBuilder:
    """Builder for ATP protocol frames with validation."""

    def __init__(self, session_id: str, tenant_id: Optional[str] = None):
        self.session_id = session_id
        self.tenant_id = tenant_id
        self.lane_sequencer = LaneSequencer()

    def build_completion_frame(
        self,
        stream_id: str,
        request: CompletionRequest,
        msg_seq: Optional[int] = None
    ) -> Frame:
        """Build a completion request frame."""
        if msg_seq is None:
            lane = Lane(persona_id=self.session_id, stream_id=stream_id)
            msg_seq = self.lane_sequencer.get_next_msg_seq(lane)

        # Build payload
        payload_content = {
            "prompt": request.prompt,
            "max_tokens": request.max_tokens,
            "quality": request.quality,
            "latency_slo_ms": request.latency_slo_ms,
            "temperature": request.temperature,
            "stream": request.stream,
        }

        if request.conversation_id:
            payload_content["conversation_id"] = request.conversation_id
        if request.consistency_level:
            payload_content["consistency_level"] = request.consistency_level

        payload = Payload(
            type="completion",
            content=payload_content
        )

        # Build meta
        meta = Meta(
            task_type="completion",
            tool_permissions=[],
            environment_id=self.tenant_id
        )

        # Build window
        window = Window(
            max_parallel=4,
            max_tokens=50000,
            max_usd_micros=1000000
        )

        return Frame(
            v=1,
            session_id=self.session_id,
            stream_id=stream_id,
            msg_seq=msg_seq,
            frag_seq=0,
            flags=[],
            qos="gold" if request.quality == "high" else "silver" if request.quality == "balanced" else "bronze",
            ttl=8,
            window=window,
            meta=meta,
            payload=payload
        )

    def build_heartbeat_frame(self, stream_id: str) -> Frame:
        """Build a heartbeat frame."""
        lane = Lane(persona_id=self.session_id, stream_id=stream_id)
        msg_seq = self.lane_sequencer.get_next_msg_seq(lane)

        payload = Payload(
            type="heartbeat",
            content={}
        )

        return Frame(
            v=1,
            session_id=self.session_id,
            stream_id=stream_id,
            msg_seq=msg_seq,
            frag_seq=0,
            flags=[],
            qos="bronze",
            ttl=8,
            window=Window(max_parallel=1, max_tokens=100, max_usd_micros=1000),
            meta=Meta(),
            payload=payload
        )

    def build_capability_frame(
        self,
        stream_id: str,
        adapter_id: str,
        adapter_type: str,
        capabilities: list[str],
        models: list[str],
        max_tokens: int | None = None,
        supported_languages: list[str] | None = None,
        cost_per_token_micros: int | None = None,
        health_endpoint: str | None = None,
        version: str | None = None,
        metadata: dict[str, Any] | None = None
    ) -> Frame:
        """Build a capability advertisement frame."""
        from .frame import CapabilityPayload

        lane = Lane(persona_id=self.session_id, stream_id=stream_id)
        msg_seq = self.lane_sequencer.get_next_msg_seq(lane)

        payload = CapabilityPayload(
            adapter_id=adapter_id,
            adapter_type=adapter_type,
            capabilities=capabilities,
            models=models,
            max_tokens=max_tokens,
            supported_languages=supported_languages,
            cost_per_token_micros=cost_per_token_micros,
            health_endpoint=health_endpoint,
            version=version,
            metadata=metadata
        )

        return Frame(
            v=1,
            session_id=self.session_id,
            stream_id=stream_id,
            msg_seq=msg_seq,
            frag_seq=0,
            flags=["capability"],
            qos="bronze",
            ttl=30,  # Longer TTL for capability frames
            window=Window(max_parallel=1, max_tokens=1000, max_usd_micros=10000),
            meta=Meta(),
            payload=payload
        )

    def build_health_frame(
        self,
        stream_id: str,
        adapter_id: str,
        status: str,
        p95_latency_ms: float | None = None,
        p50_latency_ms: float | None = None,
        p99_latency_ms: float | None = None,
        requests_per_second: float | None = None,
        error_rate: float | None = None,
        queue_depth: int | None = None,
        memory_usage_mb: float | None = None,
        cpu_usage_percent: float | None = None,
        uptime_seconds: int | None = None,
        version: str | None = None,
        metadata: dict[str, Any] | None = None
    ) -> Frame:
        """Build a health status frame."""
        from .frame import HealthPayload

        lane = Lane(persona_id=self.session_id, stream_id=stream_id)
        msg_seq = self.lane_sequencer.get_next_msg_seq(lane)

        payload = HealthPayload(
            adapter_id=adapter_id,
            status=status,
            p95_latency_ms=p95_latency_ms,
            p50_latency_ms=p50_latency_ms,
            p99_latency_ms=p99_latency_ms,
            requests_per_second=requests_per_second,
            error_rate=error_rate,
            queue_depth=queue_depth,
            memory_usage_mb=memory_usage_mb,
            cpu_usage_percent=cpu_usage_percent,
            uptime_seconds=uptime_seconds,
            version=version,
            last_health_check=time.time(),
            metadata=metadata
        )

        return Frame(
            v=1,
            session_id=self.session_id,
            stream_id=stream_id,
            msg_seq=msg_seq,
            frag_seq=0,
            flags=["health"],
            qos="bronze",
            ttl=60,  # Health frames have longer TTL
            window=Window(max_parallel=1, max_tokens=1000, max_usd_micros=10000),
            meta=Meta(),
            payload=payload
        )


class ATPWebSocketClient:
    """WebSocket client for ATP Router with automatic reconnection and retries."""

    def __init__(self, config: SDKConfig):
        self.config = config
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.frame_builder = FrameBuilder(
            session_id=config.session_id or "default_session",
            tenant_id=config.tenant_id
        )
        self.connected = False
        self._reconnect_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._response_handlers: dict[str, asyncio.Future] = {}

    async def connect(self) -> None:
        """Connect to ATP Router WebSocket endpoint."""
        if self.connected:
            return

        try:
            headers = {}
            if self.config.api_key:
                headers["x-api-key"] = self.config.api_key
            if self.config.tenant_id:
                headers["x-tenant-id"] = self.config.tenant_id

            uri = urljoin(self.config.ws_url, "/mcp")
            self.websocket = await websockets.connect(
                uri,
                extra_headers=headers,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5
            )
            self.connected = True
            logger.info("Connected to ATP Router WebSocket")

            # Start heartbeat task
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        except Exception as e:
            raise ATPConnectionError(f"Failed to connect to ATP Router: {e}") from e

    async def disconnect(self) -> None:
        """Disconnect from ATP Router."""
        self.connected = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self.websocket:
            await self.websocket.close()
            self.websocket = None

        logger.info("Disconnected from ATP Router")

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to maintain connection."""
        while self.connected:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)
                if self.connected and self.websocket:
                    heartbeat_frame = self.frame_builder.build_heartbeat_frame("heartbeat")
                    await self.websocket.send(heartbeat_frame.model_dump_json())
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
                if self.connected:
                    # Trigger reconnection
                    asyncio.create_task(self._reconnect())

    async def _reconnect(self) -> None:
        """Attempt to reconnect to the WebSocket."""
        logger.info("Attempting to reconnect...")
        await self.disconnect()
        await asyncio.sleep(self.config.retry_delay)

        for attempt in range(self.config.max_retries):
            try:
                await self.connect()
                logger.info("Reconnected successfully")
                return
            except Exception as e:
                logger.warning(f"Reconnection attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (2 ** attempt))

        raise ATPConnectionError("Failed to reconnect after maximum retries")

    async def send_frame(self, frame: Frame) -> dict[str, Any]:
        """Send a frame and wait for response."""
        if not self.connected or not self.websocket:
            raise ATPConnectionError("Not connected to ATP Router")

        # Create response handler
        response_future = asyncio.Future()
        self._response_handlers[frame.stream_id] = response_future

        try:
            # Send frame
            await self.websocket.send(frame.model_dump_json())

            # Wait for response with timeout
            response = await asyncio.wait_for(
                response_future,
                timeout=self.config.default_timeout
            )

            return response

        except asyncio.TimeoutError:
            raise ATPClientError(f"Request timeout after {self.config.default_timeout}s") from None
        except Exception as e:
            raise ATPClientError(f"Failed to send frame: {e}") from e
        finally:
            # Clean up response handler
            self._response_handlers.pop(frame.stream_id, None)

    async def _handle_messages(self) -> None:
        """Handle incoming WebSocket messages."""
        while self.connected and self.websocket:
            try:
                message = await self.websocket.recv()
                data = json.loads(message)

                # Route to appropriate handler
                stream_id = data.get("stream_id")
                if stream_id and stream_id in self._response_handlers:
                    future = self._response_handlers[stream_id]
                    if not future.done():
                        future.set_result(data)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed")
                if self.connected:
                    asyncio.create_task(self._reconnect())
                break
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")


class ATPClient:
    """Main ATP Python SDK client with HTTP and WebSocket support."""

    def __init__(self, config: SDKConfig):
        self.config = config
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.ws_client: Optional[ATPWebSocketClient] = None
        self.frame_builder = FrameBuilder(
            session_id=config.session_id or "default_session",
            tenant_id=config.tenant_id
        )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self) -> None:
        """Connect to ATP Router."""
        # Create HTTP session
        headers = {}
        if self.config.api_key:
            headers["x-api-key"] = self.config.api_key
        if self.config.tenant_id:
            headers["x-tenant-id"] = self.config.tenant_id

        self.http_session = aiohttp.ClientSession(
            base_url=self.config.base_url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=self.config.default_timeout)
        )

        # Create WebSocket client
        self.ws_client = ATPWebSocketClient(self.config)
        await self.ws_client.connect()

    async def disconnect(self) -> None:
        """Disconnect from ATP Router."""
        if self.ws_client:
            await self.ws_client.disconnect()

        if self.http_session:
            await self.http_session.close()

    async def complete(
        self,
        request: CompletionRequest,
        use_websocket: bool = True
    ) -> CompletionResponse:
        """Complete text using ATP Router."""
        if use_websocket and self.ws_client:
            return await self._complete_websocket(request)
        else:
            return await self._complete_http(request)

    async def _complete_websocket(self, request: CompletionRequest) -> CompletionResponse:
        """Complete text using WebSocket connection."""
        if not self.ws_client:
            raise ATPConnectionError("WebSocket client not initialized")

        stream_id = f"completion_{asyncio.get_event_loop().time()}"
        frame = self.frame_builder.build_completion_frame(stream_id, request)

        response_data = await self.ws_client.send_frame(frame)

        # Parse response
        if response_data.get("type") == "error":
            error = response_data.get("error", {})
            raise ATPClientError(f"ATP Router error: {error.get('message', 'Unknown error')}")

        # Extract completion data
        content = response_data.get("content", {})
        return CompletionResponse(
            text=content.get("text", ""),
            model_used=content.get("model_used", "unknown"),
            tokens_in=content.get("tokens_in", 0),
            tokens_out=content.get("tokens_out", 0),
            cost_usd=content.get("cost_usd", 0.0),
            quality_score=content.get("quality_score", 0.0)
        )

    async def _complete_http(self, request: CompletionRequest) -> CompletionResponse:
        """Complete text using HTTP endpoint."""
        if not self.http_session:
            raise ATPConnectionError("HTTP session not initialized")

        # Prepare request data
        request_data = {
            "prompt": request.prompt,
            "max_tokens": request.max_tokens,
            "quality": request.quality,
            "latency_slo_ms": request.latency_slo_ms,
            "temperature": request.temperature,
            "stream": request.stream,
        }

        if request.conversation_id:
            request_data["conversation_id"] = request.conversation_id
        if request.consistency_level:
            request_data["consistency_level"] = request.consistency_level
        if request.tenant:
            request_data["tenant"] = request.tenant

        # Make request with retries
        for attempt in range(self.config.max_retries):
            try:
                async with self.http_session.post("/v1/ask", json=request_data) as response:
                    if response.status == 200:
                        # Parse streaming response
                        return await self._parse_streaming_response(response)
                    else:
                        error_text = await response.text()
                        if response.status == 429:
                            raise ATPClientError("Rate limited")
                        elif response.status == 401:
                            raise AuthenticationError("Authentication failed")
                        else:
                            raise ATPClientError(f"HTTP {response.status}: {error_text}")

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt == self.config.max_retries - 1:
                    raise ATPConnectionError(f"Request failed after {self.config.max_retries} attempts: {e}") from e
                await asyncio.sleep(self.config.retry_delay * (2 ** attempt))

        raise ATPClientError("Request failed")

    async def _parse_streaming_response(self, response: aiohttp.ClientResponse) -> CompletionResponse:
        """Parse streaming response from HTTP endpoint."""
        text_parts = []
        final_data = {}

        async for line in response.content:
            line = line.decode('utf-8').strip()
            if not line:
                continue

            try:
                data = json.loads(line)

                if data.get("type") == "chunk":
                    text_parts.append(data.get("text", ""))
                elif data.get("type") == "final":
                    final_data = data
                    break
                elif data.get("type") == "error":
                    raise ATPClientError(f"Stream error: {data.get('error', 'Unknown error')}")

            except json.JSONDecodeError:
                continue

        return CompletionResponse(
            text="".join(text_parts),
            model_used=final_data.get("model_used", "unknown"),
            tokens_in=final_data.get("tokens_in", 0),
            tokens_out=final_data.get("tokens_out", 0),
            cost_usd=final_data.get("cost_usd", 0.0),
            quality_score=final_data.get("quality_score", 0.0)
        )

    async def health_check(self) -> bool:
        """Check if ATP Router is healthy."""
        if not self.http_session:
            return False

        try:
            async with self.http_session.get("/healthz") as response:
                return response.status == 200
        except Exception:
            return False


# Convenience functions
async def complete(
    prompt: str,
    config: Optional[SDKConfig] = None,
    **kwargs
) -> CompletionResponse:
    """Convenience function for quick completion requests."""
    if config is None:
        config = SDKConfig()

    request = CompletionRequest(prompt=prompt, **kwargs)

    async with ATPClient(config) as client:
        return await client.complete(request)


def create_client(config: SDKConfig) -> ATPClient:
    """Create an ATP client instance."""
    return ATPClient(config)
