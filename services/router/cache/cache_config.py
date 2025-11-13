"""Cache configuration management."""

import os
from dataclasses import dataclass


@dataclass
class CacheConfig:
    """Configuration for the multi-tier caching system."""

    # L1 Cache (In-Memory) Configuration
    l1_enabled: bool = True
    l1_default_ttl: int = 300  # 5 minutes
    l1_max_size: int = 1000  # Maximum number of entries
    l1_cleanup_interval: int = 60  # Cleanup interval in seconds

    # L2 Cache (Redis) Configuration
    l2_enabled: bool = True
    l2_default_ttl: int = 3600  # 1 hour
    l2_key_prefix: str = "atp:cache:"

    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"
    redis_cluster_enabled: bool = False
    redis_cluster_nodes: list[str] | None = None
    redis_max_connections: int = 20
    redis_retry_on_timeout: bool = True
    redis_socket_timeout: float = 5.0
    redis_socket_connect_timeout: float = 5.0
    redis_health_check_interval: int = 30

    # Cache Strategy Configuration
    write_through: bool = True  # Write to both L1 and L2 simultaneously
    write_behind: bool = False  # Write to L1 immediately, L2 asynchronously
    read_through: bool = True  # Read from L2 if L1 miss
    cache_null_values: bool = False  # Cache null/None values to prevent cache stampede

    # Invalidation Configuration
    invalidation_enabled: bool = True
    invalidation_batch_size: int = 100
    invalidation_timeout: float = 1.0

    # Metrics Configuration
    metrics_enabled: bool = True
    metrics_detailed: bool = False  # Detailed per-key metrics (high cardinality)

    @classmethod
    def from_environment(cls) -> "CacheConfig":
        """Create cache configuration from environment variables."""
        return cls(
            # L1 Configuration
            l1_enabled=os.getenv("CACHE_L1_ENABLED", "true").lower() == "true",
            l1_default_ttl=int(os.getenv("CACHE_L1_TTL", "300")),
            l1_max_size=int(os.getenv("CACHE_L1_MAX_SIZE", "1000")),
            l1_cleanup_interval=int(os.getenv("CACHE_L1_CLEANUP_INTERVAL", "60")),
            # L2 Configuration
            l2_enabled=os.getenv("CACHE_L2_ENABLED", "true").lower() == "true",
            l2_default_ttl=int(os.getenv("CACHE_L2_TTL", "3600")),
            l2_key_prefix=os.getenv("CACHE_L2_KEY_PREFIX", "atp:cache:"),
            # Redis Configuration
            redis_url=os.getenv("ROUTER_REDIS_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0")),
            redis_cluster_enabled=os.getenv("REDIS_CLUSTER_ENABLED", "false").lower() == "true",
            redis_cluster_nodes=_parse_cluster_nodes(os.getenv("REDIS_CLUSTER_NODES")),
            redis_max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "20")),
            redis_retry_on_timeout=os.getenv("REDIS_RETRY_ON_TIMEOUT", "true").lower() == "true",
            redis_socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT", "5.0")),
            redis_socket_connect_timeout=float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5.0")),
            redis_health_check_interval=int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30")),
            # Strategy Configuration
            write_through=os.getenv("CACHE_WRITE_THROUGH", "true").lower() == "true",
            write_behind=os.getenv("CACHE_WRITE_BEHIND", "false").lower() == "true",
            read_through=os.getenv("CACHE_READ_THROUGH", "true").lower() == "true",
            cache_null_values=os.getenv("CACHE_NULL_VALUES", "false").lower() == "true",
            # Invalidation Configuration
            invalidation_enabled=os.getenv("CACHE_INVALIDATION_ENABLED", "true").lower() == "true",
            invalidation_batch_size=int(os.getenv("CACHE_INVALIDATION_BATCH_SIZE", "100")),
            invalidation_timeout=float(os.getenv("CACHE_INVALIDATION_TIMEOUT", "1.0")),
            # Metrics Configuration
            metrics_enabled=os.getenv("CACHE_METRICS_ENABLED", "true").lower() == "true",
            metrics_detailed=os.getenv("CACHE_METRICS_DETAILED", "false").lower() == "true",
        )


def _parse_cluster_nodes(nodes_str: str | None) -> list[str] | None:
    """Parse Redis cluster nodes from environment variable."""
    if not nodes_str:
        return None

    # Support both comma-separated and JSON array formats
    if nodes_str.startswith("["):
        import json

        try:
            return json.loads(nodes_str)
        except json.JSONDecodeError:
            pass

    # Comma-separated format
    return [node.strip() for node in nodes_str.split(",") if node.strip()]
