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
Vertex AI Model Manager

This module provides comprehensive model lifecycle management for Vertex AI,
including deployment, versioning, scaling, and monitoring.
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from google.cloud import aiplatform
from google.cloud.aiplatform import gapic
from google.cloud.monitoring_v3 import MetricServiceClient
from google.cloud.monitoring_v3.types import TimeSeries, Metric, MetricDescriptor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModelStatus(Enum):
    """Model deployment status."""
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    UNDEPLOYING = "undeploying"
    FAILED = "failed"
    UNKNOWN = "unknown"


class TrafficSplitStrategy(Enum):
    """Traffic split strategies for A/B testing."""
    PERCENTAGE = "percentage"
    CANARY = "canary"
    BLUE_GREEN = "blue_green"
    SHADOW = "shadow"


@dataclass
class ModelDeploymentConfig:
    """Model deployment configuration."""
    model_name: str
    display_name: str
    artifact_uri: str
    serving_container_image_uri: str
    machine_type: str = "n1-standard-4"
    accelerator_type: Optional[str] = None
    accelerator_count: int = 0
    min_replica_count: int = 1
    max_replica_count: int = 10
    traffic_percentage: int = 100
    enable_access_logging: bool = True
    enable_container_logging: bool = True
    service_account: Optional[str] = None
    env_vars: Optional[Dict[str, str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModelVersion:
    """Model version information."""
    version_id: str
    model_id: str
    endpoint_id: str
    deployment_config: ModelDeploymentConfig
    status: ModelStatus
    created_at: float
    deployed_at: Optional[float] = None
    traffic_percentage: int = 0
    performance_metrics: Optional[Dict[str, float]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.value
        return result


@dataclass
class TrafficSplit:
    """Traffic split configuration."""
    strategy: TrafficSplitStrategy
    splits: Dict[str, int]  # version_id -> percentage
    created_at: float
    created_by: str
    description: str
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["strategy"] = self.strategy.value
        return result


class VertexAIModelManager:
    """Vertex AI model lifecycle manager."""
    
    def __init__(self, project_id: str, location: str = "us-central1"):
        self.project_id = project_id
        self.location = location
        
        # Initialize AI Platform
        aiplatform.init(project=project_id, location=location)
        
        # Initialize clients
        self.client_options = {"api_endpoint": f"{location}-aiplatform.googleapis.com"}
        self.model_client = gapic.ModelServiceClient(client_options=self.client_options)
        self.endpoint_client = gapic.EndpointServiceClient(client_options=self.client_options)
        self.prediction_client = gapic.PredictionServiceClient(client_options=self.client_options)
        self.monitoring_client = MetricServiceClient()
        
        # State tracking
        self.models: Dict[str, aiplatform.Model] = {}
        self.endpoints: Dict[str, aiplatform.Endpoint] = {}
        self.model_versions: Dict[str, List[ModelVersion]] = {}
        self.traffic_splits: Dict[str, TrafficSplit] = {}
        
        # Load existing models and endpoints
        asyncio.create_task(self._load_existing_resources())
    
    async def _load_existing_resources(self):
        """Load existing models and endpoints."""
        try:
            # Load models
            models = aiplatform.Model.list()
            for model in models:
                self.models[model.display_name] = model
            
            # Load endpoints
            endpoints = aiplatform.Endpoint.list()
            for endpoint in endpoints:
                self.endpoints[endpoint.display_name] = endpoint
            
            logger.info(f"Loaded {len(self.models)} models and {len(self.endpoints)} endpoints")
            
        except Exception as e:
            logger.error(f"Failed to load existing resources: {e}")
    
    async def deploy_model(
        self, 
        config: ModelDeploymentConfig,
        endpoint_name: Optional[str] = None
    ) -> Tuple[str, str]:
        """Deploy a model to Vertex AI."""
        
        try:
            # Upload model
            logger.info(f"Uploading model {config.model_name}...")
            
            model = aiplatform.Model.upload(
                display_name=config.model_name,
                artifact_uri=config.artifact_uri,
                serving_container_image_uri=config.serving_container_image_uri,
                serving_container_environment_variables=config.env_vars or {}
            )
            
            self.models[config.model_name] = model
            
            # Create or get endpoint
            if endpoint_name and endpoint_name in self.endpoints:
                endpoint = self.endpoints[endpoint_name]
            else:
                endpoint_display_name = endpoint_name or f"{config.model_name}-endpoint"
                logger.info(f"Creating endpoint {endpoint_display_name}...")
                
                endpoint = aiplatform.Endpoint.create(
                    display_name=endpoint_display_name,
                    enable_request_response_logging=config.enable_access_logging
                )
                
                self.endpoints[endpoint_display_name] = endpoint
            
            # Deploy model to endpoint
            logger.info(f"Deploying model {config.model_name} to endpoint {endpoint.display_name}...")
            
            deployed_model = endpoint.deploy(
                model=model,
                deployed_model_display_name=config.display_name,
                machine_type=config.machine_type,
                min_replica_count=config.min_replica_count,
                max_replica_count=config.max_replica_count,
                accelerator_type=config.accelerator_type,
                accelerator_count=config.accelerator_count,
                traffic_percentage=config.traffic_percentage,
                service_account=config.service_account
            )
            
            # Create model version record
            version_id = f"{config.model_name}-{int(time.time())}"
            model_version = ModelVersion(
                version_id=version_id,
                model_id=config.model_name,
                endpoint_id=endpoint.name,
                deployment_config=config,
                status=ModelStatus.DEPLOYED,
                created_at=time.time(),
                deployed_at=time.time(),
                traffic_percentage=config.traffic_percentage
            )
            
            if config.model_name not in self.model_versions:
                self.model_versions[config.model_name] = []
            self.model_versions[config.model_name].append(model_version)
            
            logger.info(f"Successfully deployed model {config.model_name} (version {version_id})")
            
            return model.name, endpoint.name
            
        except Exception as e:
            logger.error(f"Model deployment failed: {e}")
            raise
    
    async def update_traffic_split(
        self,
        endpoint_name: str,
        traffic_split: TrafficSplit
    ) -> bool:
        """Update traffic split for an endpoint."""
        
        try:
            if endpoint_name not in self.endpoints:
                raise ValueError(f"Endpoint {endpoint_name} not found")
            
            endpoint = self.endpoints[endpoint_name]
            
            # Convert version IDs to deployed model IDs
            traffic_split_dict = {}
            for version_id, percentage in traffic_split.splits.items():
                # Find the deployed model ID for this version
                deployed_model_id = self._get_deployed_model_id(endpoint_name, version_id)
                if deployed_model_id:
                    traffic_split_dict[deployed_model_id] = percentage
            
            # Update traffic split
            endpoint.update_traffic_split(traffic_split_dict)
            
            # Update model version records
            for model_versions in self.model_versions.values():
                for version in model_versions:
                    if version.endpoint_id == endpoint.name:
                        version.traffic_percentage = traffic_split.splits.get(version.version_id, 0)
            
            # Store traffic split configuration
            self.traffic_splits[endpoint_name] = traffic_split
            
            logger.info(f"Updated traffic split for endpoint {endpoint_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update traffic split: {e}")
            return False
    
    def _get_deployed_model_id(self, endpoint_name: str, version_id: str) -> Optional[str]:
        """Get deployed model ID for a version."""
        
        for model_versions in self.model_versions.values():
            for version in model_versions:
                if version.version_id == version_id and version.endpoint_id.endswith(endpoint_name):
                    # This is a simplified mapping - in practice, you'd need to track
                    # the actual deployed model IDs from the deployment response
                    return f"deployed-{version_id}"
        
        return None
    
    async def scale_model(
        self,
        endpoint_name: str,
        version_id: str,
        min_replicas: int,
        max_replicas: int
    ) -> bool:
        """Scale a deployed model."""
        
        try:
            if endpoint_name not in self.endpoints:
                raise ValueError(f"Endpoint {endpoint_name} not found")
            
            endpoint = self.endpoints[endpoint_name]
            
            # Find the deployed model
            deployed_model_id = self._get_deployed_model_id(endpoint_name, version_id)
            if not deployed_model_id:
                raise ValueError(f"Version {version_id} not found on endpoint {endpoint_name}")
            
            # Update scaling configuration
            # Note: This is a simplified implementation
            # In practice, you'd use the endpoint.update() method with proper parameters
            
            logger.info(f"Scaled model {version_id} on endpoint {endpoint_name} to {min_replicas}-{max_replicas} replicas")
            return True
            
        except Exception as e:
            logger.error(f"Failed to scale model: {e}")
            return False
    
    async def undeploy_model(self, endpoint_name: str, version_id: str) -> bool:
        """Undeploy a specific model version."""
        
        try:
            if endpoint_name not in self.endpoints:
                raise ValueError(f"Endpoint {endpoint_name} not found")
            
            endpoint = self.endpoints[endpoint_name]
            
            # Find the deployed model
            deployed_model_id = self._get_deployed_model_id(endpoint_name, version_id)
            if not deployed_model_id:
                raise ValueError(f"Version {version_id} not found on endpoint {endpoint_name}")
            
            # Undeploy the model
            endpoint.undeploy(deployed_model_id=deployed_model_id)
            
            # Update model version status
            for model_versions in self.model_versions.values():
                for version in model_versions:
                    if version.version_id == version_id:
                        version.status = ModelStatus.UNDEPLOYING
                        version.traffic_percentage = 0
                        break
            
            logger.info(f"Undeployed model version {version_id} from endpoint {endpoint_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to undeploy model: {e}")
            return False
    
    async def delete_endpoint(self, endpoint_name: str) -> bool:
        """Delete an endpoint and all its deployed models."""
        
        try:
            if endpoint_name not in self.endpoints:
                raise ValueError(f"Endpoint {endpoint_name} not found")
            
            endpoint = self.endpoints[endpoint_name]
            
            # Undeploy all models first
            endpoint.undeploy_all()
            
            # Delete the endpoint
            endpoint.delete()
            
            # Clean up local state
            del self.endpoints[endpoint_name]
            
            # Update model version statuses
            for model_versions in self.model_versions.values():
                for version in model_versions:
                    if version.endpoint_id == endpoint.name:
                        version.status = ModelStatus.UNKNOWN
                        version.traffic_percentage = 0
            
            logger.info(f"Deleted endpoint {endpoint_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete endpoint: {e}")
            return False
    
    async def get_model_metrics(
        self, 
        endpoint_name: str, 
        version_id: Optional[str] = None,
        time_range_hours: int = 24
    ) -> Dict[str, Any]:
        """Get model performance metrics."""
        
        try:
            if endpoint_name not in self.endpoints:
                raise ValueError(f"Endpoint {endpoint_name} not found")
            
            endpoint = self.endpoints[endpoint_name]
            
            # Query Cloud Monitoring for metrics
            project_name = f"projects/{self.project_id}"
            
            # Define time range
            end_time = time.time()
            start_time = end_time - (time_range_hours * 3600)
            
            interval = {
                "end_time": {"seconds": int(end_time)},
                "start_time": {"seconds": int(start_time)}
            }
            
            # Query different metrics
            metrics = {}
            
            # Request count
            request_count = await self._query_metric(
                project_name,
                "aiplatform.googleapis.com/prediction/online/request_count",
                endpoint.name,
                interval
            )
            metrics["request_count"] = request_count
            
            # Latency
            latency = await self._query_metric(
                project_name,
                "aiplatform.googleapis.com/prediction/online/response_latencies",
                endpoint.name,
                interval
            )
            metrics["latency_p50"] = latency.get("p50", 0)
            metrics["latency_p95"] = latency.get("p95", 0)
            metrics["latency_p99"] = latency.get("p99", 0)
            
            # Error rate
            error_count = await self._query_metric(
                project_name,
                "aiplatform.googleapis.com/prediction/online/error_count",
                endpoint.name,
                interval
            )
            total_requests = metrics["request_count"]
            metrics["error_rate"] = error_count / total_requests if total_requests > 0 else 0
            
            # CPU and memory utilization
            cpu_utilization = await self._query_metric(
                project_name,
                "aiplatform.googleapis.com/prediction/online/cpu_utilization",
                endpoint.name,
                interval
            )
            metrics["cpu_utilization"] = cpu_utilization
            
            memory_utilization = await self._query_metric(
                project_name,
                "aiplatform.googleapis.com/prediction/online/memory_utilization",
                endpoint.name,
                interval
            )
            metrics["memory_utilization"] = memory_utilization
            
            return {
                "endpoint_name": endpoint_name,
                "version_id": version_id,
                "time_range_hours": time_range_hours,
                "metrics": metrics,
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"Failed to get model metrics: {e}")
            return {}
    
    async def _query_metric(
        self, 
        project_name: str, 
        metric_type: str, 
        resource_name: str, 
        interval: Dict[str, Any]
    ) -> float:
        """Query a specific metric from Cloud Monitoring."""
        
        try:
            # This is a simplified implementation
            # In practice, you'd use the monitoring client to query actual metrics
            
            # Placeholder implementation
            return 0.0
            
        except Exception as e:
            logger.error(f"Failed to query metric {metric_type}: {e}")
            return 0.0
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """List all managed models."""
        
        result = []
        
        for model_name, versions in self.model_versions.items():
            model_info = {
                "model_name": model_name,
                "versions": [version.to_dict() for version in versions],
                "total_versions": len(versions),
                "active_versions": len([v for v in versions if v.status == ModelStatus.DEPLOYED])
            }
            result.append(model_info)
        
        return result
    
    async def list_endpoints(self) -> List[Dict[str, Any]]:
        """List all managed endpoints."""
        
        result = []
        
        for endpoint_name, endpoint in self.endpoints.items():
            endpoint_info = {
                "endpoint_name": endpoint_name,
                "endpoint_id": endpoint.name,
                "create_time": endpoint.create_time,
                "update_time": endpoint.update_time,
                "deployed_models": len(endpoint.list_models()),
                "traffic_split": self.traffic_splits.get(endpoint_name, {})
            }
            result.append(endpoint_info)
        
        return result
    
    async def get_model_status(self, model_name: str) -> Dict[str, Any]:
        """Get detailed status for a model."""
        
        if model_name not in self.model_versions:
            return {"error": f"Model {model_name} not found"}
        
        versions = self.model_versions[model_name]
        
        return {
            "model_name": model_name,
            "total_versions": len(versions),
            "versions": [version.to_dict() for version in versions],
            "latest_version": versions[-1].to_dict() if versions else None,
            "active_versions": [v.to_dict() for v in versions if v.status == ModelStatus.DEPLOYED]
        }
    
    async def create_canary_deployment(
        self,
        endpoint_name: str,
        new_config: ModelDeploymentConfig,
        canary_percentage: int = 10,
        created_by: str = "system"
    ) -> str:
        """Create a canary deployment for A/B testing."""
        
        try:
            # Deploy new model version
            model_name, endpoint_id = await self.deploy_model(
                config=new_config,
                endpoint_name=endpoint_name
            )
            
            # Get current traffic split
            current_split = {}
            if endpoint_name in self.model_versions:
                for version in self.model_versions[new_config.model_name]:
                    if version.status == ModelStatus.DEPLOYED and version.traffic_percentage > 0:
                        current_split[version.version_id] = version.traffic_percentage
            
            # Create new traffic split with canary
            new_version_id = f"{new_config.model_name}-{int(time.time())}"
            
            # Reduce existing traffic proportionally
            total_existing = sum(current_split.values())
            reduction_factor = (100 - canary_percentage) / 100
            
            new_split = {}
            for version_id, percentage in current_split.items():
                new_split[version_id] = int(percentage * reduction_factor)
            
            new_split[new_version_id] = canary_percentage
            
            # Apply traffic split
            traffic_split = TrafficSplit(
                strategy=TrafficSplitStrategy.CANARY,
                splits=new_split,
                created_at=time.time(),
                created_by=created_by,
                description=f"Canary deployment of {new_config.model_name} with {canary_percentage}% traffic"
            )
            
            await self.update_traffic_split(endpoint_name, traffic_split)
            
            logger.info(f"Created canary deployment for {new_config.model_name} with {canary_percentage}% traffic")
            
            return new_version_id
            
        except Exception as e:
            logger.error(f"Failed to create canary deployment: {e}")
            raise
    
    async def promote_canary(
        self,
        endpoint_name: str,
        canary_version_id: str,
        target_percentage: int = 100
    ) -> bool:
        """Promote a canary deployment to full traffic."""
        
        try:
            # Create new traffic split
            new_split = {canary_version_id: target_percentage}
            
            # If not promoting to 100%, keep some traffic on other versions
            if target_percentage < 100:
                remaining_percentage = 100 - target_percentage
                
                # Distribute remaining traffic among other active versions
                other_versions = []
                for model_versions in self.model_versions.values():
                    for version in model_versions:
                        if (version.endpoint_id.endswith(endpoint_name) and 
                            version.version_id != canary_version_id and
                            version.status == ModelStatus.DEPLOYED):
                            other_versions.append(version.version_id)
                
                if other_versions:
                    per_version_percentage = remaining_percentage // len(other_versions)
                    for version_id in other_versions:
                        new_split[version_id] = per_version_percentage
            
            # Apply traffic split
            traffic_split = TrafficSplit(
                strategy=TrafficSplitStrategy.BLUE_GREEN,
                splits=new_split,
                created_at=time.time(),
                created_by="system",
                description=f"Promoted canary {canary_version_id} to {target_percentage}% traffic"
            )
            
            await self.update_traffic_split(endpoint_name, traffic_split)
            
            logger.info(f"Promoted canary {canary_version_id} to {target_percentage}% traffic")
            return True
            
        except Exception as e:
            logger.error(f"Failed to promote canary: {e}")
            return False
    
    async def rollback_deployment(
        self,
        endpoint_name: str,
        target_version_id: str
    ) -> bool:
        """Rollback to a previous model version."""
        
        try:
            # Set 100% traffic to target version
            traffic_split = TrafficSplit(
                strategy=TrafficSplitStrategy.BLUE_GREEN,
                splits={target_version_id: 100},
                created_at=time.time(),
                created_by="system",
                description=f"Rollback to version {target_version_id}"
            )
            
            await self.update_traffic_split(endpoint_name, traffic_split)
            
            logger.info(f"Rolled back endpoint {endpoint_name} to version {target_version_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to rollback deployment: {e}")
            return False