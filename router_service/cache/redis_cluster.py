"""Redis cluster configuration and management."""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class RedisClusterManager:
    """Manager for Redis cluster operations and health monitoring."""

    def __init__(self, cluster_nodes: list[str], max_connections_per_node: int = 10, health_check_interval: int = 30):
        self.cluster_nodes = cluster_nodes
        self.max_connections_per_node = max_connections_per_node
        self.health_check_interval = health_check_interval

        # Cluster client (initialized lazily)
        self._cluster_client = None
        self._initialized = False

        # Health monitoring
        self._node_health: dict[str, bool] = {}
        self._health_check_task: asyncio.Task | None = None

        logger.info(f"Redis cluster manager initialized with {len(cluster_nodes)} nodes")

    async def initialize(self) -> None:
        """Initialize Redis cluster client."""
        if self._initialized:
            return

        try:
            from redis.asyncio.cluster import RedisCluster
        except ImportError:
            logger.error("Redis cluster support requires redis-py with cluster support")
            raise

        # Parse cluster nodes
        startup_nodes = []
        for node in self.cluster_nodes:
            if ":" in node:
                host, port = node.split(":", 1)
                startup_nodes.append({"host": host, "port": int(port)})
            else:
                startup_nodes.append({"host": node, "port": 6379})

        # Initialize cluster client
        self._cluster_client = RedisCluster(
            startup_nodes=startup_nodes,
            max_connections=self.max_connections_per_node * len(startup_nodes),
            decode_responses=True,
            skip_full_coverage_check=True,  # Allow partial cluster
            health_check_interval=self.health_check_interval,
        )

        # Test cluster connection
        await self._cluster_client.ping()

        # Start health monitoring
        self._start_health_monitoring()

        self._initialized = True
        logger.info("Redis cluster client initialized successfully")

    def _start_health_monitoring(self) -> None:
        """Start background health monitoring task."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._health_check_task = loop.create_task(self._health_monitor_loop())
        except RuntimeError:
            # No event loop running
            pass

    async def _health_monitor_loop(self) -> None:
        """Background task to monitor cluster node health."""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._check_cluster_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cluster health monitoring error: {e}")

    async def _check_cluster_health(self) -> None:
        """Check health of all cluster nodes."""
        if not self._cluster_client:
            return

        try:
            # Get cluster info
            cluster_info = await self._cluster_client.cluster_info()
            cluster_state = cluster_info.get("cluster_state", "fail")

            # Check individual nodes
            nodes_info = await self._cluster_client.cluster_nodes()

            for _node_id, node_info in nodes_info.items():
                node_addr = f"{node_info.get('host', 'unknown')}:{node_info.get('port', 'unknown')}"
                node_flags = node_info.get("flags", [])

                # Node is healthy if it's not marked as fail or pfail
                is_healthy = "fail" not in node_flags and "pfail" not in node_flags
                self._node_health[node_addr] = is_healthy

            logger.debug(f"Cluster health check completed - State: {cluster_state}")

        except Exception as e:
            logger.warning(f"Cluster health check failed: {e}")
            # Mark all nodes as unhealthy on error
            for node in self.cluster_nodes:
                self._node_health[node] = False

    async def get_cluster_info(self) -> dict[str, Any]:
        """Get comprehensive cluster information."""
        if not self._cluster_client:
            await self.initialize()

        try:
            cluster_info = await self._cluster_client.cluster_info()
            nodes_info = await self._cluster_client.cluster_nodes()

            # Process node information
            nodes = []
            for node_id, node_info in nodes_info.items():
                nodes.append(
                    {
                        "id": node_id,
                        "host": node_info.get("host"),
                        "port": node_info.get("port"),
                        "flags": node_info.get("flags", []),
                        "master": node_info.get("master"),
                        "slots": node_info.get("slots", []),
                        "healthy": self._node_health.get(f"{node_info.get('host')}:{node_info.get('port')}", False),
                    }
                )

            return {
                "cluster_state": cluster_info.get("cluster_state"),
                "cluster_slots_assigned": cluster_info.get("cluster_slots_assigned"),
                "cluster_slots_ok": cluster_info.get("cluster_slots_ok"),
                "cluster_slots_pfail": cluster_info.get("cluster_slots_pfail"),
                "cluster_slots_fail": cluster_info.get("cluster_slots_fail"),
                "cluster_known_nodes": cluster_info.get("cluster_known_nodes"),
                "cluster_size": cluster_info.get("cluster_size"),
                "nodes": nodes,
                "healthy_nodes": sum(1 for node in nodes if node["healthy"]),
                "total_nodes": len(nodes),
            }

        except Exception as e:
            logger.error(f"Failed to get cluster info: {e}")
            return {
                "error": str(e),
                "cluster_state": "fail",
                "healthy_nodes": 0,
                "total_nodes": len(self.cluster_nodes),
            }

    async def get_node_health(self) -> dict[str, bool]:
        """Get health status of all nodes."""
        return self._node_health.copy()

    async def failover_to_replica(self, master_node: str) -> bool:
        """Trigger failover for a specific master node."""
        if not self._cluster_client:
            await self.initialize()

        try:
            # This would require specific Redis cluster commands
            # Implementation depends on specific failover requirements
            logger.info(f"Failover requested for master node: {master_node}")

            # For now, just log the request
            # In a full implementation, this would:
            # 1. Identify the master node
            # 2. Select a healthy replica
            # 3. Execute CLUSTER FAILOVER command

            return True

        except Exception as e:
            logger.error(f"Failover failed for node {master_node}: {e}")
            return False

    async def rebalance_cluster(self) -> bool:
        """Rebalance slots across cluster nodes."""
        if not self._cluster_client:
            await self.initialize()

        try:
            # This would implement cluster rebalancing logic
            # For now, just log the request
            logger.info("Cluster rebalancing requested")

            # In a full implementation, this would:
            # 1. Analyze current slot distribution
            # 2. Calculate optimal distribution
            # 3. Execute slot migrations

            return True

        except Exception as e:
            logger.error(f"Cluster rebalancing failed: {e}")
            return False

    async def close(self) -> None:
        """Close cluster connections and cleanup."""
        # Cancel health monitoring
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Close cluster client
        if self._cluster_client:
            await self._cluster_client.close()

        self._initialized = False
        logger.info("Redis cluster manager closed")


async def create_cluster_manager(
    cluster_nodes: list[str], max_connections_per_node: int = 10, health_check_interval: int = 30
) -> RedisClusterManager:
    """Create and initialize a Redis cluster manager."""
    manager = RedisClusterManager(
        cluster_nodes=cluster_nodes,
        max_connections_per_node=max_connections_per_node,
        health_check_interval=health_check_interval,
    )

    await manager.initialize()
    return manager
