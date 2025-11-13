"""L2 (Redis) cache implementation with cluster support."""

import asyncio
import builtins
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from .cache_metrics import get_cache_metrics

logger = logging.getLogger(__name__)


class L2Cache(ABC):
    """Abstract base class for L2 cache implementations."""

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Get value from L2 cache."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set value in L2 cache."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete key from L2 cache."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists in L2 cache."""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all entries from L2 cache."""
        pass

    @abstractmethod
    async def keys(self, pattern: str = "*") -> builtins.set[str]:
        """Get keys matching pattern."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if L2 cache is healthy."""
        pass


class RedisL2Cache(L2Cache):
    """Redis-based L2 cache implementation with cluster support."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "atp:cache:",
        default_ttl: int = 3600,
        cluster_enabled: bool = False,
        cluster_nodes: list[str] | None = None,
        max_connections: int = 20,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
        retry_on_timeout: bool = True,
        enable_metrics: bool = True,
    ):
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
        self.cluster_enabled = cluster_enabled
        self.cluster_nodes = cluster_nodes or []
        self.max_connections = max_connections
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.retry_on_timeout = retry_on_timeout
        self.enable_metrics = enable_metrics

        # Redis client (initialized lazily)
        self._redis = None
        self._redis_pool = None
        self._initialized = False

        # Metrics
        self._metrics = get_cache_metrics() if enable_metrics else None

        # Health tracking
        self._last_health_check = 0.0
        self._health_status = True
        self._health_check_interval = 30.0

    async def _ensure_initialized(self) -> None:
        """Ensure Redis client is initialized."""
        if self._initialized:
            return

        try:
            if self.cluster_enabled and self.cluster_nodes:
                await self._init_cluster()
            else:
                await self._init_single()

            self._initialized = True
            logger.info("Redis L2 cache initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Redis L2 cache: {e}")
            if self._metrics:
                self._metrics.record_redis_connection_error()
            raise

    async def _init_single(self) -> None:
        """Initialize single Redis instance."""
        try:
            import redis.asyncio as redis
        except ImportError:
            import aioredis as redis

        self._redis_pool = redis.ConnectionPool.from_url(
            self.redis_url,
            max_connections=self.max_connections,
            socket_timeout=self.socket_timeout,
            socket_connect_timeout=self.socket_connect_timeout,
            retry_on_timeout=self.retry_on_timeout,
            decode_responses=True,
        )

        self._redis = redis.Redis(connection_pool=self._redis_pool)

        # Test connection
        await self._redis.ping()

        if self._metrics:
            self._metrics.record_redis_connection_created()

    async def _init_cluster(self) -> None:
        """Initialize Redis cluster."""
        try:
            import redis.asyncio as redis
            from redis.asyncio.cluster import RedisCluster
        except ImportError:
            logger.error("Redis cluster support requires redis-py with cluster support")
            raise

        startup_nodes = []
        for node in self.cluster_nodes:
            if ":" in node:
                host, port = node.split(":", 1)
                startup_nodes.append({"host": host, "port": int(port)})
            else:
                startup_nodes.append({"host": node, "port": 6379})

        self._redis = RedisCluster(
            startup_nodes=startup_nodes,
            max_connections=self.max_connections,
            socket_timeout=self.socket_timeout,
            socket_connect_timeout=self.socket_connect_timeout,
            retry_on_timeout=self.retry_on_timeout,
            decode_responses=True,
        )

        # Test connection
        await self._redis.ping()

        if self._metrics:
            self._metrics.record_redis_connection_created()

    def _make_key(self, key: str) -> str:
        """Create prefixed cache key."""
        return f"{self.key_prefix}{key}"

    def _serialize_value(self, value: Any) -> str:
        """Serialize value for Redis storage."""
        if value is None:
            return "null"

        try:
            return json.dumps(value, default=str)
        except (TypeError, ValueError) as e:
            logger.warning(f"Failed to serialize value for Redis: {e}")
            return str(value)

    def _deserialize_value(self, data: str) -> Any:
        """Deserialize value from Redis storage."""
        if data == "null":
            return None

        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            # Return as string if JSON parsing fails
            return data

    async def get(self, key: str) -> Any | None:
        """Get value from Redis cache."""
        start_time = time.time()

        try:
            await self._ensure_initialized()

            redis_key = self._make_key(key)
            data = await self._redis.get(redis_key)

            if data is None:
                if self._metrics:
                    self._metrics.record_l2_miss(key)
                return None

            value = self._deserialize_value(data)

            if self._metrics:
                self._metrics.record_l2_hit(key)

            return value

        except asyncio.TimeoutError:
            if self._metrics:
                self._metrics.record_l2_timeout()
            logger.warning(f"Redis get timeout for key: {key}")
            return None

        except Exception as e:
            if self._metrics:
                self._metrics.record_l2_error("get")
            logger.error(f"Redis get error for key {key}: {e}")
            return None

        finally:
            if self._metrics:
                duration = time.time() - start_time
                self._metrics.record_operation_duration(duration, "l2_get")

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set value in Redis cache."""
        start_time = time.time()

        try:
            await self._ensure_initialized()

            redis_key = self._make_key(key)
            serialized_value = self._serialize_value(value)
            ttl = ttl or self.default_ttl

            result = await self._redis.setex(redis_key, ttl, serialized_value)

            if self._metrics:
                self._metrics.record_l2_set(key)

            return bool(result)

        except asyncio.TimeoutError:
            if self._metrics:
                self._metrics.record_l2_timeout()
            logger.warning(f"Redis set timeout for key: {key}")
            return False

        except Exception as e:
            if self._metrics:
                self._metrics.record_l2_error("set")
            logger.error(f"Redis set error for key {key}: {e}")
            return False

        finally:
            if self._metrics:
                duration = time.time() - start_time
                self._metrics.record_operation_duration(duration, "l2_set")

    async def delete(self, key: str) -> bool:
        """Delete key from Redis cache."""
        start_time = time.time()

        try:
            await self._ensure_initialized()

            redis_key = self._make_key(key)
            result = await self._redis.delete(redis_key)

            if self._metrics:
                self._metrics.record_l2_delete(key)

            return result > 0

        except asyncio.TimeoutError:
            if self._metrics:
                self._metrics.record_l2_timeout()
            logger.warning(f"Redis delete timeout for key: {key}")
            return False

        except Exception as e:
            if self._metrics:
                self._metrics.record_l2_error("delete")
            logger.error(f"Redis delete error for key {key}: {e}")
            return False

        finally:
            if self._metrics:
                duration = time.time() - start_time
                self._metrics.record_operation_duration(duration, "l2_delete")

    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis cache."""
        try:
            await self._ensure_initialized()

            redis_key = self._make_key(key)
            result = await self._redis.exists(redis_key)

            return result > 0

        except Exception as e:
            if self._metrics:
                self._metrics.record_l2_error("exists")
            logger.error(f"Redis exists error for key {key}: {e}")
            return False

    async def clear(self) -> None:
        """Clear all cache entries with our prefix."""
        try:
            await self._ensure_initialized()

            # Get all keys with our prefix
            pattern = f"{self.key_prefix}*"
            keys = []

            if self.cluster_enabled:
                # For cluster, we need to scan all nodes
                async for key in self._redis.scan_iter(match=pattern):
                    keys.append(key)
            else:
                async for key in self._redis.scan_iter(match=pattern):
                    keys.append(key)

            # Delete in batches
            if keys:
                batch_size = 100
                for i in range(0, len(keys), batch_size):
                    batch = keys[i : i + batch_size]
                    await self._redis.delete(*batch)

            logger.info(f"Cleared {len(keys)} keys from Redis cache")

        except Exception as e:
            if self._metrics:
                self._metrics.record_l2_error("clear")
            logger.error(f"Redis clear error: {e}")

    async def keys(self, pattern: str = "*") -> builtins.set[str]:
        """Get keys matching pattern."""
        try:
            await self._ensure_initialized()

            redis_pattern = f"{self.key_prefix}{pattern}"
            keys = set()

            async for key in self._redis.scan_iter(match=redis_pattern):
                # Remove prefix from key
                if key.startswith(self.key_prefix):
                    clean_key = key[len(self.key_prefix) :]
                    keys.add(clean_key)

            return keys

        except Exception as e:
            if self._metrics:
                self._metrics.record_l2_error("keys")
            logger.error(f"Redis keys error: {e}")
            return set()

    async def health_check(self) -> bool:
        """Check Redis health."""
        current_time = time.time()

        # Use cached health status if recent
        if current_time - self._last_health_check < self._health_check_interval:
            return self._health_status

        try:
            await self._ensure_initialized()

            # Simple ping test
            result = await self._redis.ping()
            self._health_status = bool(result)

            if self._metrics:
                self._metrics.update_redis_connections(1 if self._health_status else 0)

        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")
            self._health_status = False

            if self._metrics:
                self._metrics.record_redis_connection_error()
                self._metrics.update_redis_connections(0)

        self._last_health_check = current_time
        return self._health_status

    async def get_info(self) -> dict[str, Any]:
        """Get Redis server information."""
        try:
            await self._ensure_initialized()

            info = await self._redis.info()
            return {
                "redis_version": info.get("redis_version", "unknown"),
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "cluster_enabled": self.cluster_enabled,
            }

        except Exception as e:
            logger.error(f"Failed to get Redis info: {e}")
            return {"error": str(e)}

    async def close(self) -> None:
        """Close Redis connections."""
        try:
            if self._redis:
                await self._redis.close()

            if self._redis_pool:
                await self._redis_pool.disconnect()

            self._initialized = False
            logger.info("Redis L2 cache connections closed")

        except Exception as e:
            logger.error(f"Error closing Redis connections: {e}")


class NoOpL2Cache(L2Cache):
    """No-op L2 cache implementation for when Redis is disabled."""

    async def get(self, key: str) -> Any | None:
        return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        return True

    async def delete(self, key: str) -> bool:
        return True

    async def exists(self, key: str) -> bool:
        return False

    async def clear(self) -> None:
        pass

    async def keys(self, pattern: str = "*") -> builtins.set[str]:
        return set()

    async def health_check(self) -> bool:
        return True
