"""Tests for adapter capability advertisement functionality.

Tests GAP-123: Adapter capability advertisement.
"""

import time

from router_service.adapter_registry import AdapterCapability, AdapterRegistry, get_adapter_registry
from router_service.capability_handler import CapabilityAdvertisementHandler, get_capability_handler
from router_service.frame import Frame, Meta, Payload, Window


class TestAdapterCapability:
    """Test AdapterCapability dataclass."""

    def test_adapter_capability_creation(self):
        """Test creating an AdapterCapability instance."""
        capability = AdapterCapability(
            adapter_id="test_adapter_1",
            adapter_type="ollama",
            capabilities=["text-generation", "embedding"],
            models=["llama2:7b", "codellama:13b"],
            max_tokens=4096,
            supported_languages=["en", "es"],
            cost_per_token_micros=100,
            health_endpoint="http://localhost:8080/health",
            version="1.0.0",
            metadata={"region": "us-west-2"},
        )

        assert capability.adapter_id == "test_adapter_1"
        assert capability.adapter_type == "ollama"
        assert capability.capabilities == ["text-generation", "embedding"]
        assert capability.models == ["llama2:7b", "codellama:13b"]
        assert capability.max_tokens == 4096
        assert capability.supported_languages == ["en", "es"]
        assert capability.cost_per_token_micros == 100
        assert capability.health_endpoint == "http://localhost:8080/health"
        assert capability.version == "1.0.0"
        assert capability.metadata == {"region": "us-west-2"}
        assert capability.registered_at > 0
        assert capability.last_seen > 0

    def test_update_last_seen(self):
        """Test updating last seen timestamp."""
        capability = AdapterCapability(
            adapter_id="test_adapter", adapter_type="ollama", capabilities=["text-generation"], models=["llama2:7b"]
        )

        original_last_seen = capability.last_seen
        time.sleep(0.001)  # Small delay to ensure timestamp difference
        capability.update_last_seen()

        assert capability.last_seen > original_last_seen

    def test_is_healthy(self):
        """Test health check functionality."""
        capability = AdapterCapability(
            adapter_id="test_adapter", adapter_type="ollama", capabilities=["text-generation"], models=["llama2:7b"]
        )

        # Should be healthy initially
        assert capability.is_healthy()

        # Mock old last_seen time
        capability.last_seen = time.time() - 400  # 400 seconds ago

        # Should be unhealthy after timeout
        assert not capability.is_healthy(timeout_seconds=300)


class TestAdapterRegistry:
    """Test AdapterRegistry functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.registry = AdapterRegistry()

    def test_register_capability_success(self):
        """Test successful capability registration."""
        capability_data = {
            "adapter_id": "test_adapter_1",
            "adapter_type": "ollama",
            "capabilities": ["text-generation", "embedding"],
            "models": ["llama2:7b"],
        }

        success = self.registry.register_capability(capability_data)
        assert success

        adapter = self.registry.get_adapter("test_adapter_1")
        assert adapter is not None
        assert adapter.adapter_id == "test_adapter_1"
        assert adapter.adapter_type == "ollama"
        assert adapter.capabilities == ["text-generation", "embedding"]
        assert adapter.models == ["llama2:7b"]

    def test_register_capability_missing_fields(self):
        """Test registration with missing required fields."""
        # Missing adapter_id
        capability_data = {"adapter_type": "ollama", "capabilities": ["text-generation"], "models": ["llama2:7b"]}

        success = self.registry.register_capability(capability_data)
        assert not success

    def test_register_capability_update_existing(self):
        """Test updating existing adapter capabilities."""
        # Initial registration
        capability_data = {
            "adapter_id": "test_adapter_1",
            "adapter_type": "ollama",
            "capabilities": ["text-generation"],
            "models": ["llama2:7b"],
        }

        self.registry.register_capability(capability_data)

        # Update capabilities
        updated_data = {
            "adapter_id": "test_adapter_1",
            "adapter_type": "ollama",
            "capabilities": ["text-generation", "embedding", "vision"],
            "models": ["llama2:7b", "codellama:13b"],
        }

        success = self.registry.register_capability(updated_data)
        assert success

        adapter = self.registry.get_adapter("test_adapter_1")
        assert adapter.capabilities == ["text-generation", "embedding", "vision"]
        assert adapter.models == ["llama2:7b", "codellama:13b"]

    def test_unregister_adapter(self):
        """Test unregistering an adapter."""
        # Register adapter
        capability_data = {
            "adapter_id": "test_adapter_1",
            "adapter_type": "ollama",
            "capabilities": ["text-generation"],
            "models": ["llama2:7b"],
        }

        self.registry.register_capability(capability_data)

        # Verify it's registered
        assert self.registry.get_adapter("test_adapter_1") is not None

        # Unregister
        success = self.registry.unregister_adapter("test_adapter_1")
        assert success

        # Verify it's unregistered
        assert self.registry.get_adapter("test_adapter_1") is None

    def test_unregister_unknown_adapter(self):
        """Test unregistering an unknown adapter."""
        success = self.registry.unregister_adapter("unknown_adapter")
        assert not success

    def test_get_adapters_by_type(self):
        """Test getting adapters by type."""
        # Register multiple adapters
        adapters_data = [
            {
                "adapter_id": "ollama_1",
                "adapter_type": "ollama",
                "capabilities": ["text-generation"],
                "models": ["llama2:7b"],
            },
            {
                "adapter_id": "ollama_2",
                "adapter_type": "ollama",
                "capabilities": ["embedding"],
                "models": ["embeddings:7b"],
            },
            {
                "adapter_id": "openai_1",
                "adapter_type": "openai",
                "capabilities": ["text-generation"],
                "models": ["gpt-4"],
            },
        ]

        for data in adapters_data:
            self.registry.register_capability(data)

        # Get ollama adapters
        ollama_adapters = self.registry.get_adapters_by_type("ollama")
        assert len(ollama_adapters) == 2
        adapter_ids = [a.adapter_id for a in ollama_adapters]
        assert "ollama_1" in adapter_ids
        assert "ollama_2" in adapter_ids

        # Get openai adapters
        openai_adapters = self.registry.get_adapters_by_type("openai")
        assert len(openai_adapters) == 1
        assert openai_adapters[0].adapter_id == "openai_1"

        # Get unknown type
        unknown_adapters = self.registry.get_adapters_by_type("unknown")
        assert len(unknown_adapters) == 0

    def test_get_adapter_types(self):
        """Test getting all adapter types."""
        # Register adapters of different types
        adapters_data = [
            {
                "adapter_id": "ollama_1",
                "adapter_type": "ollama",
                "capabilities": ["text-generation"],
                "models": ["llama2:7b"],
            },
            {
                "adapter_id": "openai_1",
                "adapter_type": "openai",
                "capabilities": ["text-generation"],
                "models": ["gpt-4"],
            },
            {
                "adapter_id": "anthropic_1",
                "adapter_type": "anthropic",
                "capabilities": ["text-generation"],
                "models": ["claude-3"],
            },
        ]

        for data in adapters_data:
            self.registry.register_capability(data)

        adapter_types = self.registry.get_adapter_types()
        assert len(adapter_types) == 3
        assert "ollama" in adapter_types
        assert "openai" in adapter_types
        assert "anthropic" in adapter_types

    def test_heartbeat(self):
        """Test heartbeat functionality."""
        # Register adapter
        capability_data = {
            "adapter_id": "test_adapter_1",
            "adapter_type": "ollama",
            "capabilities": ["text-generation"],
            "models": ["llama2:7b"],
        }

        self.registry.register_capability(capability_data)
        adapter = self.registry.get_adapter("test_adapter_1")
        original_last_seen = adapter.last_seen

        # Send heartbeat
        time.sleep(0.001)
        success = self.registry.heartbeat("test_adapter_1")
        assert success

        # Verify last_seen was updated
        adapter = self.registry.get_adapter("test_adapter_1")
        assert adapter.last_seen > original_last_seen

    def test_heartbeat_unknown_adapter(self):
        """Test heartbeat from unknown adapter."""
        success = self.registry.heartbeat("unknown_adapter")
        assert not success

    def test_cleanup_stale_adapters(self):
        """Test cleanup of stale adapters."""
        # Register adapter
        capability_data = {
            "adapter_id": "test_adapter_1",
            "adapter_type": "ollama",
            "capabilities": ["text-generation"],
            "models": ["llama2:7b"],
        }

        self.registry.register_capability(capability_data)

        # Verify it's registered
        assert len(self.registry.get_all_adapters()) == 1

        # Make adapter appear stale
        adapter = self.registry.get_adapter("test_adapter_1")
        adapter.last_seen = time.time() - 400  # 400 seconds ago

        # Cleanup stale adapters
        removed_count = self.registry.cleanup_stale_adapters(timeout_seconds=300)
        assert removed_count == 1

        # Verify adapter was removed
        assert len(self.registry.get_all_adapters()) == 0

    def test_update_health_telemetry_success(self):
        """Test successful health telemetry update."""
        # Register adapter
        capability_data = {
            "adapter_id": "test_adapter_1",
            "adapter_type": "ollama",
            "capabilities": ["text-generation"],
            "models": ["llama2:7b"],
        }

        self.registry.register_capability(capability_data)

        # Update health telemetry
        health_data = {
            "p95_latency_ms": 200.5,
            "p50_latency_ms": 120.3,
            "error_rate": 0.05,
            "requests_per_second": 15.2,
            "memory_usage_mb": 756.4,
        }

        success = self.registry.update_health_telemetry("test_adapter_1", health_data)
        assert success

        # Verify health data was updated
        adapter = self.registry.get_adapter("test_adapter_1")
        assert adapter.p95_latency_ms == 200.5
        assert adapter.p50_latency_ms == 120.3
        assert adapter.error_rate == 0.05
        assert adapter.requests_per_second == 15.2
        assert adapter.memory_usage_mb == 756.4
        assert adapter.last_health_update > 0

    def test_update_health_telemetry_unknown_adapter(self):
        """Test health telemetry update for unknown adapter."""
        health_data = {"p95_latency_ms": 100.0, "error_rate": 0.01}

        success = self.registry.update_health_telemetry("unknown_adapter", health_data)
        assert not success

    def test_update_health_telemetry_partial_update(self):
        """Test partial health telemetry update (only some fields)."""
        # Register adapter with initial health data
        capability_data = {
            "adapter_id": "test_adapter_1",
            "adapter_type": "ollama",
            "capabilities": ["text-generation"],
            "models": ["llama2:7b"],
            "p95_latency_ms": 150.0,
            "error_rate": 0.02,
        }

        self.registry.register_capability(capability_data)

        # Update only some fields
        health_data = {"p95_latency_ms": 180.0, "cpu_usage_percent": 55.5}

        success = self.registry.update_health_telemetry("test_adapter_1", health_data)
        assert success

        # Verify partial update
        adapter = self.registry.get_adapter("test_adapter_1")
        assert adapter.p95_latency_ms == 180.0  # Updated
        assert adapter.error_rate == 0.02  # Unchanged
        assert adapter.cpu_usage_percent == 55.5  # Added


class TestCapabilityAdvertisementHandler:
    """Test CapabilityAdvertisementHandler functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create a fresh registry for each test to avoid interference
        from router_service.adapter_registry import AdapterRegistry

        self.registry = AdapterRegistry()
        self.handler = CapabilityAdvertisementHandler()
        self.handler.registry = self.registry  # Override the global registry

    def test_process_capability_frame_success(self):
        """Test successful processing of capability frame."""
        # Create a proper payload dictionary for the capability data
        capability_data = {
            "type": "adapter.capability",
            "adapter_id": "test_adapter_1",
            "adapter_type": "ollama",
            "capabilities": ["text-generation", "embedding"],
            "models": ["llama2:7b", "codellama:13b"],
            "max_tokens": 4096,
            "supported_languages": ["en", "es"],
            "version": "1.0.0",
        }

        payload = Payload(type="adapter.capability", content=capability_data)

        frame = Frame(
            v=1,
            session_id="test_session",
            stream_id="capability_stream",
            msg_seq=1,
            frag_seq=0,
            flags=["capability"],
            qos="bronze",
            ttl=30,
            window=Window(max_parallel=1, max_tokens=1000, max_usd_micros=10000),
            meta=Meta(),
            payload=payload,
        )

        result = self.handler.process_capability_frame(frame)

        assert result["success"] is True
        assert result["adapter_id"] == "test_adapter_1"
        assert result["adapter_type"] == "ollama"
        assert "Successfully registered" in result["message"]

    def test_process_capability_frame_invalid_payload(self):
        """Test processing frame with invalid payload type."""
        # Create frame with wrong payload type
        payload = Payload(type="invalid", content={})

        frame = Frame(
            v=1,
            session_id="test_session",
            stream_id="capability_stream",
            msg_seq=1,
            frag_seq=0,
            flags=["capability"],
            qos="bronze",
            ttl=30,
            window=Window(max_parallel=1, max_tokens=1000, max_usd_micros=10000),
            meta=Meta(),
            payload=payload,
        )

        result = self.handler.process_capability_frame(frame)

        assert result["success"] is False
        # The error should be about missing required fields since the payload type check passes
        # but the capability data is empty
        assert "Failed to register adapter capability" in result["error"]

    def test_process_heartbeat_frame_success(self):
        """Test successful processing of heartbeat frame."""
        # First register an adapter
        capability_data = {
            "adapter_id": "test_adapter_1",
            "adapter_type": "ollama",
            "capabilities": ["text-generation"],
            "models": ["llama2:7b"],
        }
        self.handler.registry.register_capability(capability_data)

        # Create heartbeat payload with adapter_id
        payload = Payload(type="heartbeat", content={"adapter_id": "test_adapter_1"})

        frame = Frame(
            v=1,
            session_id="test_session",
            stream_id="heartbeat_stream",
            msg_seq=1,
            frag_seq=0,
            flags=["heartbeat"],
            qos="bronze",
            ttl=8,
            window=Window(max_parallel=1, max_tokens=100, max_usd_micros=1000),
            meta=Meta(),
            payload=payload,
        )

        result = self.handler.process_heartbeat_frame(frame)

        assert result["success"] is True
        assert "Heartbeat received" in result["message"]

    def test_process_heartbeat_frame_missing_adapter_id(self):
        """Test heartbeat frame without adapter_id."""
        payload = Payload(type="heartbeat", content={})

        frame = Frame(
            v=1,
            session_id="test_session",
            stream_id="heartbeat_stream",
            msg_seq=1,
            frag_seq=0,
            flags=["heartbeat"],
            qos="bronze",
            ttl=8,
            window=Window(max_parallel=1, max_tokens=100, max_usd_micros=1000),
            meta=Meta(),
            payload=payload,
        )

        result = self.handler.process_heartbeat_frame(frame)

        assert result["success"] is False
        assert "Missing adapter_id" in result["error"]

    def test_process_heartbeat_frame_unknown_adapter(self):
        """Test heartbeat from unknown adapter."""
        payload = Payload(type="heartbeat", content={"adapter_id": "unknown_adapter"})

        frame = Frame(
            v=1,
            session_id="test_session",
            stream_id="heartbeat_stream",
            msg_seq=1,
            frag_seq=0,
            flags=["heartbeat"],
            qos="bronze",
            ttl=8,
            window=Window(max_parallel=1, max_tokens=100, max_usd_micros=1000),
            meta=Meta(),
            payload=payload,
        )

        result = self.handler.process_heartbeat_frame(frame)

        assert result["success"] is False
        assert "Unknown adapter" in result["error"]

    def test_get_registered_adapters(self):
        """Test getting registered adapters information."""
        # Register some adapters
        adapters_data = [
            {
                "adapter_id": "ollama_1",
                "adapter_type": "ollama",
                "capabilities": ["text-generation"],
                "models": ["llama2:7b"],
                "version": "1.0.0",
            },
            {
                "adapter_id": "openai_1",
                "adapter_type": "openai",
                "capabilities": ["text-generation", "embedding"],
                "models": ["gpt-4"],
                "version": "2.0.0",
            },
        ]

        for data in adapters_data:
            self.handler.registry.register_capability(data)

        result = self.handler.get_registered_adapters()

        assert result["total_adapters"] == 2
        assert len(result["adapter_types"]) == 2
        assert "ollama" in result["adapter_types"]
        assert "openai" in result["adapter_types"]
        assert len(result["adapters"]) == 2

        # Check adapter details
        adapter_ids = [a["adapter_id"] for a in result["adapters"]]
        assert "ollama_1" in adapter_ids
        assert "openai_1" in adapter_ids

        # Check health telemetry is included
        for adapter in result["adapters"]:
            assert "p95_latency_ms" in adapter
            assert "p50_latency_ms" in adapter
            assert "error_rate" in adapter
            assert "last_health_update" in adapter

    def test_cleanup_stale_adapters(self):
        """Test cleanup of stale adapters via handler."""
        # Register adapter
        capability_data = {
            "adapter_id": "test_adapter_1",
            "adapter_type": "ollama",
            "capabilities": ["text-generation"],
            "models": ["llama2:7b"],
        }

        self.handler.registry.register_capability(capability_data)

        # Make adapter appear stale
        adapter = self.handler.registry.get_adapter("test_adapter_1")
        adapter.last_seen = time.time() - 400

        # Cleanup via handler
        result = self.handler.cleanup_stale_adapters(timeout_seconds=300)

        assert result["success"] is True
        assert result["removed_adapters"] == 1
        assert result["remaining_adapters"] == 0


class TestHealthFrameProcessing:
    """Test health frame processing functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create a fresh registry for each test to avoid interference
        from router_service.adapter_registry import AdapterRegistry

        self.registry = AdapterRegistry()
        self.handler = CapabilityAdvertisementHandler()
        self.handler.registry = self.registry

    def test_process_health_frame_success(self):
        """Test successful processing of health frame."""
        # First register an adapter
        capability_data = {
            "adapter_id": "test_adapter_1",
            "adapter_type": "ollama",
            "capabilities": ["text-generation"],
            "models": ["llama2:7b"],
        }
        self.handler.registry.register_capability(capability_data)

        # Create health data
        health_data = {
            "type": "adapter.health",
            "adapter_id": "test_adapter_1",
            "status": "healthy",
            "p95_latency_ms": 150.5,
            "p50_latency_ms": 95.2,
            "error_rate": 0.02,
            "requests_per_second": 10.5,
            "queue_depth": 3,
            "memory_usage_mb": 512.8,
            "cpu_usage_percent": 45.2,
            "uptime_seconds": 3600,
        }

        payload = Payload(type="adapter.health", content=health_data)

        frame = Frame(
            v=1,
            session_id="test_session",
            stream_id="health_stream",
            msg_seq=1,
            frag_seq=0,
            flags=["health"],
            qos="bronze",
            ttl=60,
            window=Window(max_parallel=1, max_tokens=1000, max_usd_micros=10000),
            meta=Meta(),
            payload=payload,
        )

        result = self.handler.process_health_frame(frame)

        assert result["success"] is True
        assert result["adapter_id"] == "test_adapter_1"
        assert result["status"] == "healthy"
        assert result["p95_latency_ms"] == 150.5
        assert "Health update received" in result["message"]

        # Verify health data was stored
        adapter = self.handler.registry.get_adapter("test_adapter_1")
        assert adapter.p95_latency_ms == 150.5
        assert adapter.error_rate == 0.02
        assert adapter.requests_per_second == 10.5

    def test_process_health_frame_unknown_adapter(self):
        """Test health frame for unknown adapter."""
        health_data = {
            "type": "adapter.health",
            "adapter_id": "unknown_adapter",
            "status": "healthy",
            "p95_latency_ms": 100.0,
        }

        payload = Payload(type="adapter.health", content=health_data)

        frame = Frame(
            v=1,
            session_id="test_session",
            stream_id="health_stream",
            msg_seq=1,
            frag_seq=0,
            flags=["health"],
            qos="bronze",
            ttl=60,
            window=Window(max_parallel=1, max_tokens=1000, max_usd_micros=10000),
            meta=Meta(),
            payload=payload,
        )

        result = self.handler.process_health_frame(frame)

        assert result["success"] is False
        assert "Unknown adapter" in result["error"]

    def test_process_health_frame_missing_adapter_id(self):
        """Test health frame without adapter_id."""
        health_data = {"type": "adapter.health", "status": "healthy", "p95_latency_ms": 100.0}

        payload = Payload(type="adapter.health", content=health_data)

        frame = Frame(
            v=1,
            session_id="test_session",
            stream_id="health_stream",
            msg_seq=1,
            frag_seq=0,
            flags=["health"],
            qos="bronze",
            ttl=60,
            window=Window(max_parallel=1, max_tokens=1000, max_usd_micros=10000),
            meta=Meta(),
            payload=payload,
        )

        result = self.handler.process_health_frame(frame)

        assert result["success"] is False
        assert "Missing adapter_id" in result["error"]

    def test_process_health_frame_invalid_payload(self):
        """Test health frame with invalid payload."""
        payload = Payload(type="invalid", content="not a dict")

        frame = Frame(
            v=1,
            session_id="test_session",
            stream_id="health_stream",
            msg_seq=1,
            frag_seq=0,
            flags=["health"],
            qos="bronze",
            ttl=60,
            window=Window(max_parallel=1, max_tokens=1000, max_usd_micros=10000),
            meta=Meta(),
            payload=payload,
        )

        result = self.handler.process_health_frame(frame)

        assert result["success"] is False
        assert "Invalid health data format" in result["error"]


class TestGlobalInstances:
    """Test global registry and handler instances."""

    def test_get_adapter_registry(self):
        """Test getting global adapter registry instance."""
        registry = get_adapter_registry()
        assert isinstance(registry, AdapterRegistry)

        # Test that we get the same instance
        registry2 = get_adapter_registry()
        assert registry is registry2

    def test_get_capability_handler(self):
        """Test getting global capability handler instance."""
        handler = get_capability_handler()
        assert isinstance(handler, CapabilityAdvertisementHandler)

        # Test that we get the same instance
        handler2 = get_capability_handler()
        assert handler is handler2

        # Test that handler uses the global registry
        assert handler.registry is get_adapter_registry()
