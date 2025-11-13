"""QUIC Transport Integration POC for ATP Router

This POC demonstrates QUIC transport integration with the ATP frame protocol,
including connection multiplexing, reduced latency, and proper metrics collection.
"""

import asyncio
import json
import logging
import random
import ssl
import time
from dataclasses import dataclass, field
from typing import Optional

from aiohttp import web

from metrics import REGISTRY
from router_service.frame import Frame

# QUIC-specific metrics
QUIC_SESSIONS_ACTIVE = REGISTRY.gauge("quic_sessions_active")
QUIC_CONNECTIONS_TOTAL = REGISTRY.counter("quic_connections_total")
QUIC_FRAMES_RECEIVED_TOTAL = REGISTRY.counter("quic_frames_received_total")
QUIC_LATENCY_SECONDS = REGISTRY.histogram("quic_latency_seconds", [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0])


@dataclass
class QuicConnection:
    """Represents a QUIC connection with multiple streams."""
    connection_id: str
    streams: dict[int, 'QuicStream'] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    def add_stream(self, stream_id: int) -> 'QuicStream':
        """Add a new stream to this connection."""
        stream = QuicStream(stream_id, self.connection_id)
        self.streams[stream_id] = stream
        return stream

    def get_stream(self, stream_id: int) -> Optional['QuicStream']:
        """Get a stream by ID."""
        return self.streams.get(stream_id)

    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = time.time()

    def is_expired(self, timeout: float = 300.0) -> bool:
        """Check if connection has expired."""
        return time.time() - self.last_activity > timeout


@dataclass
class QuicStream:
    """Represents a QUIC stream within a connection."""
    stream_id: int
    connection_id: str
    frames: list[Frame] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def add_frame(self, frame: Frame):
        """Add a frame to this stream."""
        self.frames.append(frame)


class QuicServer:
    """QUIC server POC for ATP frame transport."""

    def __init__(self, host: str = "localhost", port: int = 8443):
        self.host = host
        self.port = port
        self.connections: dict[str, QuicConnection] = {}
        self.stream_counter = 0
        self.logger = logging.getLogger(__name__)

        # SSL context for QUIC (simulated)
        self.ssl_context = self._create_ssl_context()

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context for QUIC connections."""
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        # In a real implementation, you'd load proper certificates
        # context.load_cert_chain('server.crt', 'server.key')
        return context

    def create_connection(self) -> QuicConnection:
        """Create a new QUIC connection."""
        connection_id = f"quic_{random.randint(1000000, 9999999)}"
        connection = QuicConnection(connection_id)
        self.connections[connection_id] = connection
        QUIC_CONNECTIONS_TOTAL.inc()
        QUIC_SESSIONS_ACTIVE.inc()
        self.logger.info(f"Created QUIC connection: {connection_id}")
        return connection

    def get_connection(self, connection_id: str) -> Optional[QuicConnection]:
        """Get a connection by ID."""
        return self.connections.get(connection_id)

    def remove_connection(self, connection_id: str):
        """Remove a connection."""
        if connection_id in self.connections:
            del self.connections[connection_id]
            QUIC_SESSIONS_ACTIVE.dec()
            self.logger.info(f"Removed QUIC connection: {connection_id}")

    def create_stream(self, connection_id: str) -> Optional[QuicStream]:
        """Create a new stream within a connection."""
        connection = self.get_connection(connection_id)
        if not connection:
            return None

        self.stream_counter += 1
        stream = connection.add_stream(self.stream_counter)
        connection.update_activity()
        return stream

    async def handle_frame(self, connection_id: str, stream_id: int, frame_data: bytes) -> bytes:
        """Handle incoming frame over QUIC transport."""
        start_time = time.time()

        try:
            # For POC, assume frame_data is JSON (simplified)
            # In real implementation, this would use CBOR decoding
            frame_dict = json.loads(frame_data.decode('utf-8'))
            QUIC_FRAMES_RECEIVED_TOTAL.inc()

            # Get or create connection and stream
            connection = self.get_connection(connection_id)
            if not connection:
                connection = self.create_connection()

            stream = connection.get_stream(stream_id)
            if not stream:
                stream = self.create_stream(connection_id)
                if not stream:
                    raise ValueError("Failed to create stream")

            # Add frame to stream
            stream.add_frame(frame_dict)
            connection.update_activity()

            # Process frame (simplified response)
            response_frame = {
                "msg_seq": frame_dict.get("msg_seq", 0),
                "status": "processed",
                "quic_transport": True,
                "timestamp": time.time()
            }

            processing_time = time.time() - start_time
            QUIC_LATENCY_SECONDS.observe(processing_time)

            return json.dumps(response_frame).encode('utf-8')

        except Exception as e:
            self.logger.error(f"Error handling QUIC frame: {e}")
            # Return error frame
            error_frame = {
                "error": str(e),
                "timestamp": time.time()
            }
            return json.dumps(error_frame).encode('utf-8')

    async def cleanup_expired_connections(self):
        """Clean up expired connections."""
        while True:
            await asyncio.sleep(60)  # Check every minute
            expired = [
                conn_id for conn_id, conn in self.connections.items()
                if conn.is_expired()
            ]
            for conn_id in expired:
                self.remove_connection(conn_id)
                self.logger.info(f"Cleaned up expired connection: {conn_id}")

    def get_stats(self) -> dict:
        """Get QUIC server statistics."""
        return {
            "active_connections": len(self.connections),
            "total_connections": QUIC_CONNECTIONS_TOTAL._value,
            "total_frames_received": QUIC_FRAMES_RECEIVED_TOTAL._value,
            "connections": [
                {
                    "id": conn.connection_id,
                    "streams": len(conn.streams),
                    "age_seconds": time.time() - conn.created_at,
                    "last_activity_seconds": time.time() - conn.last_activity
                }
                for conn in self.connections.values()
            ]
        }


class HttpQuicAdapter:
    """Adapter to simulate QUIC over HTTP for testing purposes."""

    def __init__(self, quic_server: QuicServer):
        self.quic_server = quic_server
        self.app = web.Application()
        self.app.router.add_post('/quic/frame', self.handle_frame)
        self.app.router.add_get('/quic/stats', self.handle_stats)

    async def handle_frame(self, request: web.Request) -> web.Response:
        """Handle frame over HTTP (simulating QUIC)."""
        try:
            data = await request.json()
            connection_id = data.get('connection_id', 'default')
            stream_id = data.get('stream_id', 1)
            frame_data = bytes.fromhex(data['frame_hex'])

            response_data = await self.quic_server.handle_frame(
                connection_id, stream_id, frame_data
            )

            return web.json_response({
                'response_hex': response_data.hex(),
                'status': 'ok'
            })

        except Exception as e:
            return web.json_response({
                'error': str(e),
                'status': 'error'
            }, status=400)

    async def handle_stats(self, request: web.Request) -> web.Response:
        """Get QUIC server statistics."""
        stats = self.quic_server.get_stats()
        return web.json_response(stats)


async def main():
    """Main function to run QUIC server POC."""
    logging.basicConfig(level=logging.INFO)

    # Create QUIC server
    quic_server = QuicServer()

    # Create HTTP adapter for testing
    adapter = HttpQuicAdapter(quic_server)

    # Start cleanup task
    asyncio.create_task(quic_server.cleanup_expired_connections())

    # Start HTTP server (simulating QUIC endpoint)
    runner = web.AppRunner(adapter.app)
    await runner.setup()
    site = web.TCPSite(runner, quic_server.host, quic_server.port)
    await site.start()

    print(f"QUIC Server POC running on {quic_server.host}:{quic_server.port}")
    print("Use HTTP POST to /quic/frame to simulate QUIC frames")
    print("Use HTTP GET to /quic/stats to get server statistics")

    # Keep running
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        print("Shutting down QUIC server...")
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
