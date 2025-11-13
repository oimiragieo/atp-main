"""Capability advertisement handler for processing adapter capability frames.

Implements GAP-123: Adapter capability advertisement.
"""

from __future__ import annotations

import logging
from typing import Any

from .adapter_registry import get_adapter_registry
from .frame import Frame, Payload

logger = logging.getLogger(__name__)


class CapabilityAdvertisementHandler:
    """Handler for processing adapter capability advertisement frames."""

    def __init__(self) -> None:
        self.registry = get_adapter_registry()

    def process_capability_frame(self, frame: Frame) -> dict[str, Any]:
        """Process a capability advertisement frame.

        Args:
            frame: The capability advertisement frame to process

        Returns:
            Response dictionary with processing result
        """
        try:
            # Validate frame type
            if not isinstance(frame.payload, Payload):
                return {
                    "success": False,
                    "error": "Invalid payload type for capability frame"
                }

            # Extract capability data from payload content
            capability_data = frame.payload.content
            if not isinstance(capability_data, dict):
                return {
                    "success": False,
                    "error": "Invalid capability data format"
                }

            # Register the capability
            success = self.registry.register_capability(capability_data)

            if success:
                adapter_id = capability_data.get("adapter_id", "unknown")
                adapter_type = capability_data.get("adapter_type", "unknown")
                return {
                    "success": True,
                    "message": f"Successfully registered adapter {adapter_id}",
                    "adapter_id": adapter_id,
                    "adapter_type": adapter_type
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to register adapter capability"
                }

        except Exception as e:
            logger.error(f"Error processing capability frame: {e}")
            return {
                "success": False,
                "error": f"Internal error: {str(e)}"
            }

    def process_heartbeat_frame(self, frame: Frame) -> dict[str, Any]:
        """Process a heartbeat frame from an adapter.

        Args:
            frame: The heartbeat frame to process

        Returns:
            Response dictionary with processing result
        """
        try:
            # Extract adapter_id from frame payload content
            adapter_id = None

            if isinstance(frame.payload, Payload) and isinstance(frame.payload.content, dict):
                adapter_id = frame.payload.content.get("adapter_id")

            # Also check meta as fallback
            if not adapter_id and hasattr(frame, 'meta') and frame.meta:
                adapter_id = getattr(frame.meta, 'adapter_id', None)

            if not adapter_id:
                return {
                    "success": False,
                    "error": "Missing adapter_id in heartbeat frame"
                }

            # Update heartbeat
            success = self.registry.heartbeat(adapter_id)

            if success:
                return {
                    "success": True,
                    "message": f"Heartbeat received from adapter {adapter_id}"
                }
            else:
                return {
                    "success": False,
                    "error": f"Unknown adapter: {adapter_id}"
                }

        except Exception as e:
            logger.error(f"Error processing heartbeat frame: {e}")
            return {
                "success": False,
                "error": f"Internal error: {str(e)}"
            }

    def process_health_frame(self, frame: Frame) -> dict[str, Any]:
        """Process a health status frame from an adapter.

        Args:
            frame: The health frame to process

        Returns:
            Response dictionary with processing result
        """
        try:
            # Validate frame type
            if not isinstance(frame.payload, Payload):
                return {
                    "success": False,
                    "error": "Invalid payload type for health frame"
                }

            # Extract health data from payload content
            health_data = frame.payload.content
            if not isinstance(health_data, dict):
                return {
                    "success": False,
                    "error": "Invalid health data format"
                }

            adapter_id = health_data.get("adapter_id")
            if not adapter_id:
                return {
                    "success": False,
                    "error": "Missing adapter_id in health frame"
                }

            # Update adapter health status in registry
            success = self.registry.update_health_telemetry(adapter_id, health_data)

            if success:
                # Also update heartbeat (last seen time)
                self.registry.heartbeat(adapter_id)

                # Update metrics
                from metrics.registry import ADAPTER_HEALTH_UPDATES
                ADAPTER_HEALTH_UPDATES.inc()

                # Store health telemetry data (could be extended to store in registry)
                health_status = health_data.get("status", "unknown")
                p95_latency = health_data.get("p95_latency_ms")

                return {
                    "success": True,
                    "message": f"Health update received from adapter {adapter_id}",
                    "adapter_id": adapter_id,
                    "status": health_status,
                    "p95_latency_ms": p95_latency
                }
            else:
                return {
                    "success": False,
                    "error": f"Unknown adapter: {adapter_id}"
                }

        except Exception as e:
            logger.error(f"Error processing health frame: {e}")
            return {
                "success": False,
                "error": f"Internal error: {str(e)}"
            }

    def get_registered_adapters(self) -> dict[str, Any]:
        """Get information about all registered adapters.

        Returns:
            Dictionary with adapter information
        """
        adapters = self.registry.get_all_adapters()
        adapter_types = self.registry.get_adapter_types()

        return {
            "total_adapters": len(adapters),
            "adapter_types": adapter_types,
            "adapters": [
                {
                    "adapter_id": adapter.adapter_id,
                    "adapter_type": adapter.adapter_type,
                    "capabilities": adapter.capabilities,
                    "models": adapter.models,
                    "max_tokens": adapter.max_tokens,
                    "supported_languages": adapter.supported_languages,
                    "version": adapter.version,
                    "last_seen": adapter.last_seen,
                    "healthy": adapter.is_healthy(),
                    "p95_latency_ms": adapter.p95_latency_ms,
                    "p50_latency_ms": adapter.p50_latency_ms,
                    "p99_latency_ms": adapter.p99_latency_ms,
                    "requests_per_second": adapter.requests_per_second,
                    "error_rate": adapter.error_rate,
                    "queue_depth": adapter.queue_depth,
                    "memory_usage_mb": adapter.memory_usage_mb,
                    "cpu_usage_percent": adapter.cpu_usage_percent,
                    "uptime_seconds": adapter.uptime_seconds,
                    "last_health_update": adapter.last_health_update
                }
                for adapter in adapters
            ]
        }

    def cleanup_stale_adapters(self, timeout_seconds: int = 300) -> dict[str, Any]:
        """Clean up stale adapters and return cleanup statistics.

        Args:
            timeout_seconds: Timeout for considering adapters stale

        Returns:
            Dictionary with cleanup results
        """
        removed_count = self.registry.cleanup_stale_adapters(timeout_seconds)

        return {
            "success": True,
            "removed_adapters": removed_count,
            "remaining_adapters": len(self.registry.get_all_adapters())
        }


# Global handler instance
_capability_handler = CapabilityAdvertisementHandler()


def get_capability_handler() -> CapabilityAdvertisementHandler:
    """Get the global capability advertisement handler instance."""
    return _capability_handler


def generate_tool_descriptors() -> list[dict[str, Any]]:
    """Generate MCP tool descriptors from registered adapter capabilities.

    Returns:
        List of MCP tool descriptor dictionaries
    """
    from metrics.registry import TOOLS_EXPOSED_TOTAL
    
    handler = get_capability_handler()
    adapters = handler.registry.get_all_adapters()

    tools = []

    # Always include the main routing tool
    routing_tool = {
        "name": "route.complete",
        "description": "Adaptive completion (cost/quality optimized) using registered adapters",
        "inputSchema": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {"type": "string", "description": "The text prompt to complete"},
                "quality_target": {
                    "type": "string",
                    "enum": ["fast", "balanced", "high"],
                    "default": "balanced",
                    "description": "Quality target for completion"
                },
                "max_cost_usd": {
                    "type": "number",
                    "default": 0.05,
                    "description": "Maximum cost budget in USD"
                },
                "latency_slo_ms": {
                    "type": "integer",
                    "default": 2000,
                    "description": "Latency service level objective in milliseconds"
                },
                "adapter_type": {
                    "type": "string",
                    "enum": list({adapter.adapter_type for adapter in adapters}),
                    "description": "Specific adapter type to use (optional)"
                }
            },
        },
    }
    tools.append(routing_tool)

    # Generate adapter-specific tools
    for adapter in adapters:
        if adapter.is_healthy():  # Only include healthy adapters
            adapter_tool = {
                "name": f"adapter.{adapter.adapter_id}",
                "description": f"Direct access to {adapter.adapter_id} ({adapter.adapter_type})",
                "inputSchema": {
                    "type": "object",
                    "required": ["prompt"],
                    "properties": {
                        "prompt": {"type": "string", "description": "The text prompt to process"},
                        "max_tokens": {
                            "type": "integer",
                            "default": adapter.max_tokens or 512,
                            "description": "Maximum tokens to generate"
                        },
                        "model": {
                            "type": "string",
                            "enum": adapter.models,
                            "default": adapter.models[0] if adapter.models else None,
                            "description": "Specific model to use"
                        }
                    },
                },
            }
            tools.append(adapter_tool)

    # Update metrics
    TOOLS_EXPOSED_TOTAL.set(len(tools))
    
    return tools
