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

"""
Multi-Region Active-Active Architecture

This module provides comprehensive multi-region support for the ATP platform,
including region-aware service discovery, load balancing, database replication,
and Redis cluster federation.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import random
import threading
from concurrent.futures import ThreadPoolExecutor
import aiohttp
import asyncpg
import redis.asyncio as redis
from redis.asyncio.cluster import RedisCluster
import consul
import etcd3

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RegionStatus(Enum):
    """Region status enumeration."""
    ACTIVE = "active"
    DEGRADED = "degraded"
    FAILED = "failed"
    MAINTENANCE = "maintenance"


class ServiceType(Enum):
    """Service type enumeration."""
    ROUTER = "router"
    MEMORY_GATEWAY = "memory_gateway"
    ADAPTER = "adapter"
    DATABASE = "database"
    REDIS = "redis"
    LOAD_BALANCER = "load_balancer"


@dataclass
class Region:
    """Region configuration and metadata."""
    id: str
    name: str
    cloud_provider: str
    location: str
    datacenter: str
    status: RegionStatus
    priority: int
    latency_zones: List[str]
    compliance_zones: List[str]
    created_at: datetime
    last_health_check: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "cloud_provider": self.cloud_provider,
            "location": self.location,
            "datacenter": self.datacenter,
            "status": self.status.value,
            "priority": self.priority,
            "latency_zones": self.latency_zones,
            "compliance_zones": self.compliance_zones,
            "created_at": self.created_at.isoformat(),
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None
        }


@dataclass
class ServiceInstance:
    """Service instance registration."""
    id: str
    service_type: ServiceType
    region_id: str
    host: str
    port: int
    health_endpoint: str
    metadata: Dict[str, Any]
    registered_at: datetime
    last_heartbeat: Optional[datetime] = None
    healthy: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "service_type": self.service_type.value,
            "region_id": self.region_id,
            "host": self.host,
            "port": self.port,
            "health_endpoint": self.health_endpoint,
            "metadata": self.metadata,
            "registered_at": self.registered_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "healthy": self.healthy
        }


@dataclass
class LoadBalancingRule:
    """Load balancing rule configuration."""
    id: str
    name: str
    service_type: ServiceType
    algorithm: str  # round_robin, weighted, least_connections, geographic
    weights: Dict[str, float]
    health_check_required: bool
    sticky_sessions: bool
    failover_regions: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "service_type": self.service_type.value,
            "algorithm": self.algorithm,
            "weights": self.weights,
            "health_check_required": self.health_check_required,
            "sticky_sessions": self.sticky_sessions,
            "failover_regions": self.failover_regions
        }


class ServiceDiscovery:
    """Region-aware service discovery system."""
    
    def __init__(self, consul_host: str = "localhost", consul_port: int = 8500):
        self.consul_host = consul_host
        self.consul_port = consul_port
        self.consul_client = consul.Consul(host=consul_host, port=consul_port)
        self.regions: Dict[str, Region] = {}
        self.services: Dict[str, ServiceInstance] = {}
        self.load_balancing_rules: Dict[str, LoadBalancingRule] = {}
        self.health_check_interval = 30  # seconds
        self.monitoring_active = False
        self.monitor_thread = None
        
    def register_region(self, region: Region):
        """Register a new region."""
        self.regions[region.id] = region
        
        # Register region in Consul
        try:
            self.consul_client.kv.put(
                f"atp/regions/{region.id}",
                json.dumps(region.to_dict())
            )
            logger.info(f"Registered region {region.id} ({region.name})")
        except Exception as e:
            logger.error(f"Failed to register region {region.id}: {e}")
    
    def register_service(self, service: ServiceInstance):
        """Register a service instance."""
        self.services[service.id] = service
        
        # Register service in Consul
        try:
            self.consul_client.agent.service.register(
                name=f"atp-{service.service_type.value}",
                service_id=service.id,
                address=service.host,
                port=service.port,
                tags=[
                    f"region:{service.region_id}",
                    f"type:{service.service_type.value}",
                    "atp-service"
                ],
                check=consul.Check.http(
                    f"http://{service.host}:{service.port}{service.health_endpoint}",
                    interval="30s",
                    timeout="10s"
                ),
                meta=service.metadata
            )
            logger.info(f"Registered service {service.id} in region {service.region_id}")
        except Exception as e:
            logger.error(f"Failed to register service {service.id}: {e}")
    
    def discover_services(
        self, 
        service_type: ServiceType, 
        region_id: Optional[str] = None,
        healthy_only: bool = True
    ) -> List[ServiceInstance]:
        """Discover services by type and region."""
        try:
            # Query Consul for services
            services = self.consul_client.health.service(
                f"atp-{service_type.value}",
                passing=healthy_only
            )[1]
            
            result = []
            for service_data in services:
                service_info = service_data['Service']
                
                # Filter by region if specified
                if region_id:
                    region_tag = f"region:{region_id}"
                    if region_tag not in service_info.get('Tags', []):
                        continue
                
                # Create ServiceInstance from Consul data
                instance = ServiceInstance(
                    id=service_info['ID'],
                    service_type=service_type,
                    region_id=self._extract_region_from_tags(service_info.get('Tags', [])),
                    host=service_info['Address'],
                    port=service_info['Port'],
                    health_endpoint="/health",  # Default
                    metadata=service_info.get('Meta', {}),
                    registered_at=datetime.now(timezone.utc),
                    healthy=True
                )
                result.append(instance)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to discover services: {e}")
            return []
    
    def _extract_region_from_tags(self, tags: List[str]) -> str:
        """Extract region ID from service tags."""
        for tag in tags:
            if tag.startswith("region:"):
                return tag.split(":", 1)[1]
        return "unknown"
    
    def get_healthy_regions(self) -> List[Region]:
        """Get list of healthy regions."""
        healthy_regions = []
        for region in self.regions.values():
            if region.status == RegionStatus.ACTIVE:
                healthy_regions.append(region)
        return sorted(healthy_regions, key=lambda r: r.priority)
    
    def start_monitoring(self):
        """Start health monitoring."""
        if self.monitoring_active:
            return
            
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True
        )
        self.monitor_thread.start()
        logger.info("Started service discovery monitoring")
    
    def stop_monitoring(self):
        """Stop health monitoring."""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Stopped service discovery monitoring")
    
    def _monitoring_loop(self):
        """Health monitoring loop."""
        while self.monitoring_active:
            try:
                self._update_region_health()
                self._update_service_health()
                time.sleep(self.health_check_interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(5)
    
    def _update_region_health(self):
        """Update region health status."""
        for region in self.regions.values():
            try:
                # Check if region has healthy services
                services = self.discover_services(
                    ServiceType.ROUTER, 
                    region.id, 
                    healthy_only=True
                )
                
                if services:
                    region.status = RegionStatus.ACTIVE
                else:
                    region.status = RegionStatus.DEGRADED
                
                region.last_health_check = datetime.now(timezone.utc)
                
            except Exception as e:
                logger.error(f"Error checking region {region.id} health: {e}")
                region.status = RegionStatus.FAILED
    
    def _update_service_health(self):
        """Update service health status."""
        for service in self.services.values():
            try:
                # Consul handles health checks automatically
                # We just update our local cache
                service.last_heartbeat = datetime.now(timezone.utc)
            except Exception as e:
                logger.error(f"Error updating service {service.id} health: {e}")


class LoadBalancer:
    """Region-aware load balancer."""
    
    def __init__(self, service_discovery: ServiceDiscovery):
        self.service_discovery = service_discovery
        self.session_store = {}  # In production, use Redis
        self.connection_counts = {}
        
    def select_service(
        self, 
        service_type: ServiceType,
        client_region: Optional[str] = None,
        session_id: Optional[str] = None,
        request_metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[ServiceInstance]:
        """Select optimal service instance based on load balancing rules."""
        
        # Get load balancing rule for service type
        rule = self._get_load_balancing_rule(service_type)
        
        # Handle sticky sessions
        if rule.sticky_sessions and session_id:
            cached_service = self.session_store.get(session_id)
            if cached_service and self._is_service_healthy(cached_service):
                return cached_service
        
        # Get available services
        services = self._get_available_services(service_type, client_region, rule)
        
        if not services:
            return None
        
        # Apply load balancing algorithm
        selected_service = self._apply_load_balancing_algorithm(services, rule, request_metadata)
        
        # Cache for sticky sessions
        if rule.sticky_sessions and session_id and selected_service:
            self.session_store[session_id] = selected_service
        
        return selected_service
    
    def _get_load_balancing_rule(self, service_type: ServiceType) -> LoadBalancingRule:
        """Get load balancing rule for service type."""
        rule_id = f"default_{service_type.value}"
        
        if rule_id not in self.service_discovery.load_balancing_rules:
            # Create default rule
            default_rule = LoadBalancingRule(
                id=rule_id,
                name=f"Default {service_type.value} rule",
                service_type=service_type,
                algorithm="geographic",
                weights={},
                health_check_required=True,
                sticky_sessions=False,
                failover_regions=[]
            )
            self.service_discovery.load_balancing_rules[rule_id] = default_rule
        
        return self.service_discovery.load_balancing_rules[rule_id]
    
    def _get_available_services(
        self, 
        service_type: ServiceType, 
        client_region: Optional[str],
        rule: LoadBalancingRule
    ) -> List[ServiceInstance]:
        """Get available services based on region and health."""
        
        services = []
        
        # Try client region first
        if client_region:
            region_services = self.service_discovery.discover_services(
                service_type, client_region, rule.health_check_required
            )
            services.extend(region_services)
        
        # If no services in client region, try other regions
        if not services:
            all_services = self.service_discovery.discover_services(
                service_type, None, rule.health_check_required
            )
            services.extend(all_services)
        
        return services
    
    def _apply_load_balancing_algorithm(
        self, 
        services: List[ServiceInstance], 
        rule: LoadBalancingRule,
        request_metadata: Optional[Dict[str, Any]]
    ) -> Optional[ServiceInstance]:
        """Apply load balancing algorithm to select service."""
        
        if not services:
            return None
        
        if rule.algorithm == "round_robin":
            return self._round_robin_selection(services)
        elif rule.algorithm == "weighted":
            return self._weighted_selection(services, rule.weights)
        elif rule.algorithm == "least_connections":
            return self._least_connections_selection(services)
        elif rule.algorithm == "geographic":
            return self._geographic_selection(services, request_metadata)
        else:
            # Default to round robin
            return self._round_robin_selection(services)
    
    def _round_robin_selection(self, services: List[ServiceInstance]) -> ServiceInstance:
        """Round robin service selection."""
        # Simple round robin based on current time
        index = int(time.time()) % len(services)
        return services[index]
    
    def _weighted_selection(self, services: List[ServiceInstance], weights: Dict[str, float]) -> ServiceInstance:
        """Weighted service selection."""
        if not weights:
            return self._round_robin_selection(services)
        
        # Calculate weighted selection
        total_weight = sum(weights.get(s.region_id, 1.0) for s in services)
        random_value = random.uniform(0, total_weight)
        
        current_weight = 0
        for service in services:
            current_weight += weights.get(service.region_id, 1.0)
            if random_value <= current_weight:
                return service
        
        return services[0]  # Fallback
    
    def _least_connections_selection(self, services: List[ServiceInstance]) -> ServiceInstance:
        """Least connections service selection."""
        min_connections = float('inf')
        selected_service = services[0]
        
        for service in services:
            connections = self.connection_counts.get(service.id, 0)
            if connections < min_connections:
                min_connections = connections
                selected_service = service
        
        return selected_service
    
    def _geographic_selection(
        self, 
        services: List[ServiceInstance], 
        request_metadata: Optional[Dict[str, Any]]
    ) -> ServiceInstance:
        """Geographic proximity service selection."""
        if not request_metadata or "client_region" not in request_metadata:
            return self._round_robin_selection(services)
        
        client_region = request_metadata["client_region"]
        
        # Prefer services in the same region
        same_region_services = [s for s in services if s.region_id == client_region]
        if same_region_services:
            return self._round_robin_selection(same_region_services)
        
        # Fallback to any available service
        return self._round_robin_selection(services)
    
    def _is_service_healthy(self, service: ServiceInstance) -> bool:
        """Check if service is healthy."""
        return service.healthy and service.last_heartbeat and \
               (datetime.now(timezone.utc) - service.last_heartbeat).seconds < 60
    
    def record_connection(self, service_id: str):
        """Record new connection to service."""
        self.connection_counts[service_id] = self.connection_counts.get(service_id, 0) + 1
    
    def release_connection(self, service_id: str):
        """Release connection from service."""
        if service_id in self.connection_counts:
            self.connection_counts[service_id] = max(0, self.connection_counts[service_id] - 1)


class DatabaseReplication:
    """Cross-region PostgreSQL database replication manager."""
    
    def __init__(self):
        self.primary_regions = {}
        self.replica_regions = {}
        self.replication_slots = {}
        self.monitoring_active = False
        self.monitor_thread = None
        
    async def setup_streaming_replication(
        self, 
        primary_region: str,
        primary_host: str,
        replica_region: str,
        replica_host: str,
        replication_user: str,
        replication_password: str
    ):
        """Set up PostgreSQL streaming replication between regions."""
        
        try:
            # Connect to primary database
            primary_conn = await asyncpg.connect(
                host=primary_host,
                user=replication_user,
                password=replication_password,
                database="postgres"
            )
            
            # Create replication slot
            slot_name = f"atp_replica_{replica_region}"
            await primary_conn.execute(
                f"SELECT pg_create_physical_replication_slot('{slot_name}')"
            )
            
            self.replication_slots[replica_region] = {
                "slot_name": slot_name,
                "primary_region": primary_region,
                "primary_host": primary_host,
                "replica_region": replica_region,
                "replica_host": replica_host,
                "created_at": datetime.now(timezone.utc)
            }
            
            await primary_conn.close()
            
            logger.info(f"Set up replication from {primary_region} to {replica_region}")
            
        except Exception as e:
            logger.error(f"Failed to set up replication: {e}")
            raise
    
    async def monitor_replication_lag(self) -> Dict[str, Dict[str, Any]]:
        """Monitor replication lag across all replicas."""
        lag_info = {}
        
        for replica_region, slot_info in self.replication_slots.items():
            try:
                # Connect to primary
                primary_conn = await asyncpg.connect(
                    host=slot_info["primary_host"],
                    user="postgres",  # Use appropriate user
                    database="postgres"
                )
                
                # Query replication lag
                lag_query = """
                SELECT 
                    slot_name,
                    active,
                    pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) as lag_bytes,
                    pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn) as flush_lag_bytes
                FROM pg_replication_slots 
                WHERE slot_name = $1
                """
                
                result = await primary_conn.fetchrow(lag_query, slot_info["slot_name"])
                
                if result:
                    lag_info[replica_region] = {
                        "slot_name": result["slot_name"],
                        "active": result["active"],
                        "lag_bytes": result["lag_bytes"] or 0,
                        "flush_lag_bytes": result["flush_lag_bytes"] or 0,
                        "lag_mb": (result["lag_bytes"] or 0) / (1024 * 1024),
                        "last_checked": datetime.now(timezone.utc).isoformat()
                    }
                
                await primary_conn.close()
                
            except Exception as e:
                logger.error(f"Failed to check replication lag for {replica_region}: {e}")
                lag_info[replica_region] = {
                    "error": str(e),
                    "last_checked": datetime.now(timezone.utc).isoformat()
                }
        
        return lag_info
    
    async def promote_replica(self, replica_region: str):
        """Promote a replica to primary (for failover)."""
        try:
            if replica_region not in self.replication_slots:
                raise ValueError(f"No replication slot found for region {replica_region}")
            
            slot_info = self.replication_slots[replica_region]
            
            # Connect to replica
            replica_conn = await asyncpg.connect(
                host=slot_info["replica_host"],
                user="postgres",
                database="postgres"
            )
            
            # Promote replica to primary
            await replica_conn.execute("SELECT pg_promote()")
            
            await replica_conn.close()
            
            logger.info(f"Promoted replica in region {replica_region} to primary")
            
        except Exception as e:
            logger.error(f"Failed to promote replica {replica_region}: {e}")
            raise


class RedisClusterFederation:
    """Cross-region Redis cluster federation manager."""
    
    def __init__(self):
        self.clusters = {}
        self.federation_config = {}
        self.sync_active = False
        self.sync_thread = None
        
    def register_cluster(
        self, 
        region_id: str, 
        cluster_nodes: List[str],
        is_primary: bool = False
    ):
        """Register a Redis cluster for a region."""
        try:
            cluster = RedisCluster(
                startup_nodes=[{"host": node.split(":")[0], "port": int(node.split(":")[1])} 
                              for node in cluster_nodes],
                decode_responses=True,
                skip_full_coverage_check=True
            )
            
            self.clusters[region_id] = {
                "cluster": cluster,
                "nodes": cluster_nodes,
                "is_primary": is_primary,
                "last_sync": None,
                "sync_errors": 0
            }
            
            logger.info(f"Registered Redis cluster for region {region_id}")
            
        except Exception as e:
            logger.error(f"Failed to register Redis cluster for {region_id}: {e}")
            raise
    
    async def setup_cross_region_sync(
        self, 
        primary_region: str, 
        replica_regions: List[str],
        sync_patterns: List[str] = None
    ):
        """Set up cross-region data synchronization."""
        
        if sync_patterns is None:
            sync_patterns = ["atp:*", "session:*", "cache:*"]
        
        self.federation_config = {
            "primary_region": primary_region,
            "replica_regions": replica_regions,
            "sync_patterns": sync_patterns,
            "sync_interval": 5,  # seconds
            "batch_size": 1000
        }
        
        logger.info(f"Set up cross-region sync from {primary_region} to {replica_regions}")
    
    async def start_sync(self):
        """Start cross-region synchronization."""
        if self.sync_active:
            return
            
        self.sync_active = True
        self.sync_thread = threading.Thread(
            target=self._sync_loop,
            daemon=True
        )
        self.sync_thread.start()
        logger.info("Started Redis cross-region sync")
    
    def stop_sync(self):
        """Stop cross-region synchronization."""
        self.sync_active = False
        if self.sync_thread:
            self.sync_thread.join(timeout=10)
        logger.info("Stopped Redis cross-region sync")
    
    def _sync_loop(self):
        """Cross-region synchronization loop."""
        while self.sync_active:
            try:
                asyncio.run(self._perform_sync())
                time.sleep(self.federation_config.get("sync_interval", 5))
            except Exception as e:
                logger.error(f"Error in Redis sync loop: {e}")
                time.sleep(10)
    
    async def _perform_sync(self):
        """Perform cross-region data synchronization."""
        if not self.federation_config:
            return
        
        primary_region = self.federation_config["primary_region"]
        replica_regions = self.federation_config["replica_regions"]
        sync_patterns = self.federation_config["sync_patterns"]
        
        if primary_region not in self.clusters:
            logger.error(f"Primary region {primary_region} not found in clusters")
            return
        
        primary_cluster = self.clusters[primary_region]["cluster"]
        
        try:
            # Get keys to sync from primary
            keys_to_sync = set()
            for pattern in sync_patterns:
                keys = await primary_cluster.keys(pattern)
                keys_to_sync.update(keys)
            
            if not keys_to_sync:
                return
            
            # Get data from primary
            pipe = primary_cluster.pipeline()
            for key in keys_to_sync:
                pipe.dump(key)
                pipe.ttl(key)
            
            results = await pipe.execute()
            
            # Prepare data for replication
            key_data = {}
            for i, key in enumerate(keys_to_sync):
                data_index = i * 2
                ttl_index = i * 2 + 1
                
                if data_index < len(results) and results[data_index]:
                    key_data[key] = {
                        "data": results[data_index],
                        "ttl": results[ttl_index] if ttl_index < len(results) else -1
                    }
            
            # Replicate to replica regions
            for replica_region in replica_regions:
                if replica_region in self.clusters:
                    await self._replicate_to_region(replica_region, key_data)
            
        except Exception as e:
            logger.error(f"Error performing Redis sync: {e}")
    
    async def _replicate_to_region(self, region_id: str, key_data: Dict[str, Dict]):
        """Replicate data to a specific region."""
        try:
            replica_cluster = self.clusters[region_id]["cluster"]
            
            pipe = replica_cluster.pipeline()
            for key, data in key_data.items():
                pipe.restore(key, data["ttl"], data["data"], replace=True)
            
            await pipe.execute()
            
            self.clusters[region_id]["last_sync"] = datetime.now(timezone.utc)
            self.clusters[region_id]["sync_errors"] = 0
            
        except Exception as e:
            logger.error(f"Error replicating to region {region_id}: {e}")
            self.clusters[region_id]["sync_errors"] += 1


class ConfigurationManager:
    """Region-specific configuration management and policy distribution."""
    
    def __init__(self, etcd_host: str = "localhost", etcd_port: int = 2379):
        self.etcd_client = etcd3.client(host=etcd_host, port=etcd_port)
        self.config_cache = {}
        self.policy_cache = {}
        self.watchers = {}
        
    def set_region_config(self, region_id: str, config_key: str, config_value: Any):
        """Set configuration for a specific region."""
        try:
            key = f"/atp/regions/{region_id}/config/{config_key}"
            value = json.dumps(config_value) if not isinstance(config_value, str) else config_value
            
            self.etcd_client.put(key, value)
            
            # Update cache
            if region_id not in self.config_cache:
                self.config_cache[region_id] = {}
            self.config_cache[region_id][config_key] = config_value
            
            logger.info(f"Set config {config_key} for region {region_id}")
            
        except Exception as e:
            logger.error(f"Failed to set config for region {region_id}: {e}")
    
    def get_region_config(self, region_id: str, config_key: str, default: Any = None) -> Any:
        """Get configuration for a specific region."""
        try:
            # Check cache first
            if region_id in self.config_cache and config_key in self.config_cache[region_id]:
                return self.config_cache[region_id][config_key]
            
            # Get from etcd
            key = f"/atp/regions/{region_id}/config/{config_key}"
            result = self.etcd_client.get(key)
            
            if result[0] is not None:
                value = result[0].decode('utf-8')
                try:
                    parsed_value = json.loads(value)
                except json.JSONDecodeError:
                    parsed_value = value
                
                # Update cache
                if region_id not in self.config_cache:
                    self.config_cache[region_id] = {}
                self.config_cache[region_id][config_key] = parsed_value
                
                return parsed_value
            
            return default
            
        except Exception as e:
            logger.error(f"Failed to get config for region {region_id}: {e}")
            return default
    
    def distribute_policy(self, policy_id: str, policy_data: Dict[str, Any], target_regions: List[str] = None):
        """Distribute policy to regions."""
        try:
            if target_regions is None:
                # Distribute to all regions
                target_regions = ["global"]
            
            for region_id in target_regions:
                key = f"/atp/regions/{region_id}/policies/{policy_id}"
                value = json.dumps(policy_data)
                
                self.etcd_client.put(key, value)
                
                # Update cache
                if region_id not in self.policy_cache:
                    self.policy_cache[region_id] = {}
                self.policy_cache[region_id][policy_id] = policy_data
            
            logger.info(f"Distributed policy {policy_id} to regions {target_regions}")
            
        except Exception as e:
            logger.error(f"Failed to distribute policy {policy_id}: {e}")
    
    def watch_config_changes(self, region_id: str, callback):
        """Watch for configuration changes in a region."""
        try:
            key_prefix = f"/atp/regions/{region_id}/config/"
            
            def watch_callback(event):
                try:
                    if event.type == etcd3.events.PutEvent:
                        key = event.key.decode('utf-8')
                        value = event.value.decode('utf-8')
                        config_key = key.replace(key_prefix, "")
                        
                        try:
                            parsed_value = json.loads(value)
                        except json.JSONDecodeError:
                            parsed_value = value
                        
                        callback(config_key, parsed_value)
                        
                except Exception as e:
                    logger.error(f"Error in config watch callback: {e}")
            
            watch_id = self.etcd_client.add_watch_prefix_callback(key_prefix, watch_callback)
            self.watchers[f"{region_id}_config"] = watch_id
            
            logger.info(f"Started watching config changes for region {region_id}")
            
        except Exception as e:
            logger.error(f"Failed to watch config changes for region {region_id}: {e}")


class MultiRegionManager:
    """Main multi-region architecture manager."""
    
    def __init__(self):
        self.service_discovery = ServiceDiscovery()
        self.load_balancer = LoadBalancer(self.service_discovery)
        self.db_replication = DatabaseReplication()
        self.redis_federation = RedisClusterFederation()
        self.config_manager = ConfigurationManager()
        self.initialized = False
        
    async def initialize(self, config: Dict[str, Any]):
        """Initialize multi-region architecture."""
        try:
            # Initialize regions
            for region_config in config.get("regions", []):
                region = Region(
                    id=region_config["id"],
                    name=region_config["name"],
                    cloud_provider=region_config["cloud_provider"],
                    location=region_config["location"],
                    datacenter=region_config["datacenter"],
                    status=RegionStatus.ACTIVE,
                    priority=region_config.get("priority", 100),
                    latency_zones=region_config.get("latency_zones", []),
                    compliance_zones=region_config.get("compliance_zones", []),
                    created_at=datetime.now(timezone.utc)
                )
                self.service_discovery.register_region(region)
            
            # Set up database replication
            db_config = config.get("database_replication", {})
            if db_config:
                await self._setup_database_replication(db_config)
            
            # Set up Redis federation
            redis_config = config.get("redis_federation", {})
            if redis_config:
                await self._setup_redis_federation(redis_config)
            
            # Start monitoring
            self.service_discovery.start_monitoring()
            await self.redis_federation.start_sync()
            
            self.initialized = True
            logger.info("Multi-region architecture initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize multi-region architecture: {e}")
            raise
    
    async def _setup_database_replication(self, config: Dict[str, Any]):
        """Set up database replication based on configuration."""
        primary_region = config.get("primary_region")
        replicas = config.get("replicas", [])
        
        for replica_config in replicas:
            await self.db_replication.setup_streaming_replication(
                primary_region=primary_region,
                primary_host=config["primary_host"],
                replica_region=replica_config["region"],
                replica_host=replica_config["host"],
                replication_user=config["replication_user"],
                replication_password=config["replication_password"]
            )
    
    async def _setup_redis_federation(self, config: Dict[str, Any]):
        """Set up Redis federation based on configuration."""
        primary_region = config.get("primary_region")
        
        for region_id, cluster_config in config.get("clusters", {}).items():
            self.redis_federation.register_cluster(
                region_id=region_id,
                cluster_nodes=cluster_config["nodes"],
                is_primary=(region_id == primary_region)
            )
        
        replica_regions = [r for r in config.get("clusters", {}).keys() if r != primary_region]
        await self.redis_federation.setup_cross_region_sync(
            primary_region=primary_region,
            replica_regions=replica_regions,
            sync_patterns=config.get("sync_patterns", ["atp:*"])
        )
    
    def get_service_endpoint(
        self, 
        service_type: ServiceType, 
        client_region: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Get optimal service endpoint for a client."""
        service = self.load_balancer.select_service(
            service_type=service_type,
            client_region=client_region,
            session_id=session_id
        )
        
        if service:
            return f"http://{service.host}:{service.port}"
        
        return None
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status of multi-region architecture."""
        try:
            # Region health
            regions_health = {}
            for region_id, region in self.service_discovery.regions.items():
                regions_health[region_id] = {
                    "status": region.status.value,
                    "last_health_check": region.last_health_check.isoformat() if region.last_health_check else None,
                    "priority": region.priority
                }
            
            # Database replication health
            db_health = await self.db_replication.monitor_replication_lag()
            
            # Redis federation health
            redis_health = {}
            for region_id, cluster_info in self.redis_federation.clusters.items():
                redis_health[region_id] = {
                    "last_sync": cluster_info["last_sync"].isoformat() if cluster_info["last_sync"] else None,
                    "sync_errors": cluster_info["sync_errors"],
                    "is_primary": cluster_info["is_primary"]
                }
            
            return {
                "initialized": self.initialized,
                "regions": regions_health,
                "database_replication": db_health,
                "redis_federation": redis_health,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting health status: {e}")
            return {"error": str(e)}
    
    async def shutdown(self):
        """Shutdown multi-region architecture."""
        try:
            self.service_discovery.stop_monitoring()
            self.redis_federation.stop_sync()
            
            # Close Redis connections
            for cluster_info in self.redis_federation.clusters.values():
                await cluster_info["cluster"].close()
            
            logger.info("Multi-region architecture shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")


# Example configuration
EXAMPLE_CONFIG = {
    "regions": [
        {
            "id": "us-east-1",
            "name": "US East (Virginia)",
            "cloud_provider": "aws",
            "location": "us-east-1",
            "datacenter": "us-east-1a",
            "priority": 1,
            "latency_zones": ["us-east", "us-central"],
            "compliance_zones": ["us", "global"]
        },
        {
            "id": "eu-west-1",
            "name": "EU West (Ireland)",
            "cloud_provider": "aws",
            "location": "eu-west-1",
            "datacenter": "eu-west-1a",
            "priority": 2,
            "latency_zones": ["eu-west", "eu-central"],
            "compliance_zones": ["eu", "gdpr", "global"]
        },
        {
            "id": "ap-southeast-1",
            "name": "Asia Pacific (Singapore)",
            "cloud_provider": "aws",
            "location": "ap-southeast-1",
            "datacenter": "ap-southeast-1a",
            "priority": 3,
            "latency_zones": ["ap-southeast", "ap-east"],
            "compliance_zones": ["apac", "global"]
        }
    ],
    "database_replication": {
        "primary_region": "us-east-1",
        "primary_host": "db-primary.us-east-1.amazonaws.com",
        "replication_user": "replicator",
        "replication_password": "secure_password",
        "replicas": [
            {
                "region": "eu-west-1",
                "host": "db-replica.eu-west-1.amazonaws.com"
            },
            {
                "region": "ap-southeast-1",
                "host": "db-replica.ap-southeast-1.amazonaws.com"
            }
        ]
    },
    "redis_federation": {
        "primary_region": "us-east-1",
        "clusters": {
            "us-east-1": {
                "nodes": ["redis-1.us-east-1:6379", "redis-2.us-east-1:6379", "redis-3.us-east-1:6379"]
            },
            "eu-west-1": {
                "nodes": ["redis-1.eu-west-1:6379", "redis-2.eu-west-1:6379", "redis-3.eu-west-1:6379"]
            },
            "ap-southeast-1": {
                "nodes": ["redis-1.ap-southeast-1:6379", "redis-2.ap-southeast-1:6379", "redis-3.ap-southeast-1:6379"]
            }
        },
        "sync_patterns": ["atp:*", "session:*", "cache:*", "routing:*"]
    }
}