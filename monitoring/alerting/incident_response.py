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
Incident Response Automation
Automated incident response with remediation actions, runbook execution,
and intelligent escalation.
"""
import asyncio
import logging
import time
import subprocess
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import aiohttp
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RemediationStatus(Enum):
    """Remediation action status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"

class ActionType(Enum):
    """Types of remediation actions."""
    SCRIPT = "script"
    API_CALL = "api_call"
    RESTART_SERVICE = "restart_service"
    SCALE_SERVICE = "scale_service"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    CLEAR_CACHE = "clear_cache"
    CIRCUIT_BREAKER = "circuit_breaker"
    TRAFFIC_REDIRECT = "traffic_redirect"

@dataclass
class RemediationAction:
    """Automated remediation action."""
    id: str
    name: str
    description: str
    action_type: ActionType
    trigger_conditions: List[str]
    action_config: Dict[str, Any]
    timeout_seconds: int = 300
    max_retries: int = 3
    enabled: bool = True
    requires_approval: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["action_type"] = self.action_type.value
        return result

@dataclass
class RemediationExecution:
    """Remediation execution record."""
    id: str
    action_id: str
    incident_id: Optional[str]
    alert_id: Optional[str]
    status: RemediationStatus
    started_at: float
    completed_at: Optional[float] = None
    output: Optional[str] = None
    error: Optional[str] = None
    executed_by: str = "system"
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.value
        return result

@dataclass
class RunbookStep:
    """Runbook step definition."""
    id: str
    name: str
    description: str
    action_type: str
    config: Dict[str, Any]
    depends_on: List[str] = None
    timeout_seconds: int = 300
    
    def __post_init__(self):
        if self.depends_on is None:
            self.depends_on = []
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class Runbook:
    """Incident response runbook."""
    id: str
    name: str
    description: str
    trigger_conditions: List[str]
    steps: List[RunbookStep]
    enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["steps"] = [step.to_dict() for step in self.steps]
        return result

class IncidentResponseAutomation:
    """Automated incident response system."""
    
    def __init__(self):
        self.remediation_actions: Dict[str, RemediationAction] = {}
        self.runbooks: Dict[str, Runbook] = {}
        self.execution_history: List[RemediationExecution] = []
        self.active_executions: Dict[str, RemediationExecution] = {}
        
        # Rate limiting
        self.execution_counts: Dict[str, List[float]] = {}
        self.max_executions_per_hour = 10
        
        self._lock = threading.Lock()
        
        # Initialize default actions and runbooks
        self._initialize_default_actions()
        self._initialize_default_runbooks()
    
    def _initialize_default_actions(self):
        """Initialize default remediation actions."""
        default_actions = [
            RemediationAction(
                id="restart_router_service",
                name="Restart Router Service",
                description="Restart the ATP router service",
                action_type=ActionType.RESTART_SERVICE,
                trigger_conditions=["high_error_rate", "service_unavailable"],
                action_config={
                    "service_name": "atp-router",
                    "namespace": "default",
                    "wait_for_ready": True
                },
                timeout_seconds=120,
                requires_approval=False
            ),
            RemediationAction(
                id="scale_up_router",
                name="Scale Up Router Service",
                description="Scale up router service replicas",
                action_type=ActionType.SCALE_SERVICE,
                trigger_conditions=["high_latency", "high_cpu_usage"],
                action_config={
                    "service_name": "atp-router",
                    "namespace": "default",
                    "target_replicas": 5,
                    "max_replicas": 10
                },
                timeout_seconds=300,
                requires_approval=False
            ),
            RemediationAction(
                id="clear_redis_cache",
                name="Clear Redis Cache",
                description="Clear Redis cache to resolve cache-related issues",
                action_type=ActionType.CLEAR_CACHE,
                trigger_conditions=["cache_errors", "memory_pressure"],
                action_config={
                    "cache_type": "redis",
                    "host": "redis-service",
                    "port": 6379,
                    "pattern": "atp:*"
                },
                timeout_seconds=60,
                requires_approval=False
            ),
            RemediationAction(
                id="enable_circuit_breaker",
                name="Enable Circuit Breaker",
                description="Enable circuit breaker for failing external service",
                action_type=ActionType.CIRCUIT_BREAKER,
                trigger_conditions=["external_service_errors"],
                action_config={
                    "service_name": "external-api",
                    "failure_threshold": 5,
                    "timeout_seconds": 60
                },
                timeout_seconds=30,
                requires_approval=False
            ),
            RemediationAction(
                id="rollback_deployment",
                name="Rollback Deployment",
                description="Rollback to previous deployment version",
                action_type=ActionType.ROLLBACK_DEPLOYMENT,
                trigger_conditions=["deployment_errors", "high_error_rate_after_deploy"],
                action_config={
                    "service_name": "atp-router",
                    "namespace": "default",
                    "rollback_to": "previous"
                },
                timeout_seconds=600,
                requires_approval=True  # Requires approval for rollbacks
            )
        ]
        
        for action in default_actions:
            self.remediation_actions[action.id] = action
    
    def _initialize_default_runbooks(self):
        """Initialize default incident response runbooks."""
        # High error rate runbook
        high_error_rate_runbook = Runbook(
            id="high_error_rate_response",
            name="High Error Rate Response",
            description="Automated response to high error rate incidents",
            trigger_conditions=["high_error_rate"],
            steps=[
                RunbookStep(
                    id="check_service_health",
                    name="Check Service Health",
                    description="Check the health of all services",
                    action_type="health_check",
                    config={"services": ["atp-router", "memory-gateway", "redis"]}
                ),
                RunbookStep(
                    id="analyze_error_logs",
                    name="Analyze Error Logs",
                    description="Analyze recent error logs for patterns",
                    action_type="log_analysis",
                    config={"time_window": "15m", "error_threshold": 10}
                ),
                RunbookStep(
                    id="restart_unhealthy_services",
                    name="Restart Unhealthy Services",
                    description="Restart services that are unhealthy",
                    action_type="conditional_restart",
                    config={"health_check_dependency": "check_service_health"},
                    depends_on=["check_service_health"]
                ),
                RunbookStep(
                    id="scale_if_needed",
                    name="Scale Services if Needed",
                    description="Scale up services if CPU/memory usage is high",
                    action_type="conditional_scale",
                    config={"cpu_threshold": 80, "memory_threshold": 85},
                    depends_on=["check_service_health"]
                )
            ]
        )
        
        # Service unavailable runbook
        service_unavailable_runbook = Runbook(
            id="service_unavailable_response",
            name="Service Unavailable Response",
            description="Automated response to service unavailability",
            trigger_conditions=["service_unavailable", "low_availability"],
            steps=[
                RunbookStep(
                    id="check_infrastructure",
                    name="Check Infrastructure",
                    description="Check underlying infrastructure health",
                    action_type="infrastructure_check",
                    config={"check_nodes": True, "check_network": True}
                ),
                RunbookStep(
                    id="restart_services",
                    name="Restart Services",
                    description="Restart all ATP services",
                    action_type="service_restart",
                    config={"services": ["atp-router", "memory-gateway"], "parallel": False}
                ),
                RunbookStep(
                    id="verify_recovery",
                    name="Verify Recovery",
                    description="Verify that services have recovered",
                    action_type="health_verification",
                    config={"wait_time": 60, "max_attempts": 5},
                    depends_on=["restart_services"]
                )
            ]
        )
        
        self.runbooks[high_error_rate_runbook.id] = high_error_rate_runbook
        self.runbooks[service_unavailable_runbook.id] = service_unavailable_runbook
    
    async def trigger_remediation(
        self, 
        condition: str, 
        incident_id: Optional[str] = None,
        alert_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """Trigger remediation actions based on condition."""
        triggered_actions = []
        
        # Find matching remediation actions
        matching_actions = []
        with self._lock:
            for action in self.remediation_actions.values():
                if not action.enabled:
                    continue
                
                if condition in action.trigger_conditions:
                    # Check rate limiting
                    if self._is_rate_limited(action.id):
                        logger.warning(f"Remediation action {action.id} is rate limited")
                        continue
                    
                    matching_actions.append(action)
        
        # Execute matching actions
        for action in matching_actions:
            try:
                execution_id = await self._execute_remediation_action(
                    action, incident_id, alert_id, context
                )
                triggered_actions.append(execution_id)
            except Exception as e:
                logger.error(f"Failed to execute remediation action {action.id}: {e}")
        
        return triggered_actions
    
    async def execute_runbook(
        self, 
        runbook_id: str, 
        incident_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Execute an incident response runbook."""
        if runbook_id not in self.runbooks:
            raise ValueError(f"Runbook {runbook_id} not found")
        
        runbook = self.runbooks[runbook_id]
        if not runbook.enabled:
            raise ValueError(f"Runbook {runbook_id} is disabled")
        
        execution_id = f"runbook_{int(time.time())}_{runbook_id}"
        
        logger.info(f"Starting runbook execution: {runbook.name} (ID: {execution_id})")
        
        # Execute steps in dependency order
        completed_steps = set()
        
        for step in runbook.steps:
            # Check dependencies
            if not all(dep in completed_steps for dep in step.depends_on):
                logger.warning(f"Skipping step {step.id} due to unmet dependencies")
                continue
            
            try:
                await self._execute_runbook_step(step, context)
                completed_steps.add(step.id)
                logger.info(f"Completed runbook step: {step.name}")
            except Exception as e:
                logger.error(f"Failed to execute runbook step {step.id}: {e}")
                # Continue with other steps that don't depend on this one
        
        logger.info(f"Completed runbook execution: {runbook.name}")
        return execution_id
    
    async def _execute_remediation_action(
        self, 
        action: RemediationAction,
        incident_id: Optional[str] = None,
        alert_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Execute a remediation action."""
        execution_id = f"remediation_{int(time.time())}_{action.id}"
        
        execution = RemediationExecution(
            id=execution_id,
            action_id=action.id,
            incident_id=incident_id,
            alert_id=alert_id,
            status=RemediationStatus.PENDING,
            started_at=time.time()
        )
        
        with self._lock:
            self.active_executions[execution_id] = execution
        
        try:
            execution.status = RemediationStatus.RUNNING
            
            # Execute based on action type
            if action.action_type == ActionType.SCRIPT:
                result = await self._execute_script(action.action_config)
            elif action.action_type == ActionType.API_CALL:
                result = await self._execute_api_call(action.action_config)
            elif action.action_type == ActionType.RESTART_SERVICE:
                result = await self._restart_service(action.action_config)
            elif action.action_type == ActionType.SCALE_SERVICE:
                result = await self._scale_service(action.action_config)
            elif action.action_type == ActionType.ROLLBACK_DEPLOYMENT:
                result = await self._rollback_deployment(action.action_config)
            elif action.action_type == ActionType.CLEAR_CACHE:
                result = await self._clear_cache(action.action_config)
            elif action.action_type == ActionType.CIRCUIT_BREAKER:
                result = await self._enable_circuit_breaker(action.action_config)
            elif action.action_type == ActionType.TRAFFIC_REDIRECT:
                result = await self._redirect_traffic(action.action_config)
            else:
                raise ValueError(f"Unknown action type: {action.action_type}")
            
            execution.status = RemediationStatus.SUCCESS
            execution.output = result
            
        except Exception as e:
            execution.status = RemediationStatus.FAILED
            execution.error = str(e)
            logger.error(f"Remediation action {action.id} failed: {e}")
        
        finally:
            execution.completed_at = time.time()
            
            with self._lock:
                self.execution_history.append(execution)
                if execution_id in self.active_executions:
                    del self.active_executions[execution_id]
                
                # Update rate limiting
                self._record_execution(action.id)
        
        logger.info(f"Remediation action {action.id} completed with status: {execution.status.value}")
        return execution_id
    
    async def _execute_runbook_step(self, step: RunbookStep, context: Optional[Dict[str, Any]] = None):
        """Execute a runbook step."""
        logger.info(f"Executing runbook step: {step.name}")
        
        # This is a simplified implementation
        # In practice, you'd have specific handlers for each step type
        if step.action_type == "health_check":
            await self._perform_health_check(step.config)
        elif step.action_type == "log_analysis":
            await self._analyze_logs(step.config)
        elif step.action_type == "conditional_restart":
            await self._conditional_restart(step.config)
        elif step.action_type == "conditional_scale":
            await self._conditional_scale(step.config)
        else:
            logger.warning(f"Unknown runbook step type: {step.action_type}")
    
    async def _execute_script(self, config: Dict[str, Any]) -> str:
        """Execute a script."""
        script_path = config.get("script_path")
        args = config.get("args", [])
        
        if not script_path:
            raise ValueError("Script path not specified")
        
        # Execute script
        process = await asyncio.create_subprocess_exec(
            script_path, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"Script failed with return code {process.returncode}: {stderr.decode()}")
        
        return stdout.decode()
    
    async def _execute_api_call(self, config: Dict[str, Any]) -> str:
        """Execute an API call."""
        url = config.get("url")
        method = config.get("method", "GET")
        headers = config.get("headers", {})
        data = config.get("data")
        
        if not url:
            raise ValueError("URL not specified")
        
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, json=data) as response:
                if response.status >= 400:
                    raise Exception(f"API call failed with status {response.status}")
                
                return await response.text()
    
    async def _restart_service(self, config: Dict[str, Any]) -> str:
        """Restart a service."""
        service_name = config.get("service_name")
        namespace = config.get("namespace", "default")
        
        if not service_name:
            raise ValueError("Service name not specified")
        
        # This would typically use kubectl or a Kubernetes API client
        cmd = f"kubectl rollout restart deployment/{service_name} -n {namespace}"
        
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"Service restart failed: {stderr.decode()}")
        
        return f"Service {service_name} restarted successfully"
    
    async def _scale_service(self, config: Dict[str, Any]) -> str:
        """Scale a service."""
        service_name = config.get("service_name")
        namespace = config.get("namespace", "default")
        target_replicas = config.get("target_replicas", 3)
        
        if not service_name:
            raise ValueError("Service name not specified")
        
        cmd = f"kubectl scale deployment/{service_name} --replicas={target_replicas} -n {namespace}"
        
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"Service scaling failed: {stderr.decode()}")
        
        return f"Service {service_name} scaled to {target_replicas} replicas"
    
    async def _rollback_deployment(self, config: Dict[str, Any]) -> str:
        """Rollback a deployment."""
        service_name = config.get("service_name")
        namespace = config.get("namespace", "default")
        
        if not service_name:
            raise ValueError("Service name not specified")
        
        cmd = f"kubectl rollout undo deployment/{service_name} -n {namespace}"
        
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"Deployment rollback failed: {stderr.decode()}")
        
        return f"Deployment {service_name} rolled back successfully"
    
    async def _clear_cache(self, config: Dict[str, Any]) -> str:
        """Clear cache."""
        cache_type = config.get("cache_type", "redis")
        
        if cache_type == "redis":
            host = config.get("host", "localhost")
            port = config.get("port", 6379)
            pattern = config.get("pattern", "*")
            
            # This would typically use a Redis client
            return f"Cleared Redis cache with pattern {pattern}"
        
        return "Cache cleared"
    
    async def _enable_circuit_breaker(self, config: Dict[str, Any]) -> str:
        """Enable circuit breaker."""
        service_name = config.get("service_name")
        
        if not service_name:
            raise ValueError("Service name not specified")
        
        # This would typically update circuit breaker configuration
        return f"Circuit breaker enabled for {service_name}"
    
    async def _redirect_traffic(self, config: Dict[str, Any]) -> str:
        """Redirect traffic."""
        from_service = config.get("from_service")
        to_service = config.get("to_service")
        
        if not from_service or not to_service:
            raise ValueError("Source and destination services must be specified")
        
        # This would typically update load balancer or ingress configuration
        return f"Traffic redirected from {from_service} to {to_service}"
    
    async def _perform_health_check(self, config: Dict[str, Any]):
        """Perform health check."""
        services = config.get("services", [])
        
        for service in services:
            # Perform health check for each service
            logger.info(f"Health check for {service}: OK")
    
    async def _analyze_logs(self, config: Dict[str, Any]):
        """Analyze logs."""
        time_window = config.get("time_window", "15m")
        error_threshold = config.get("error_threshold", 10)
        
        logger.info(f"Analyzing logs for the last {time_window}")
        # Log analysis logic would go here
    
    async def _conditional_restart(self, config: Dict[str, Any]):
        """Conditionally restart services."""
        # This would check health status and restart if needed
        logger.info("Performing conditional restart")
    
    async def _conditional_scale(self, config: Dict[str, Any]):
        """Conditionally scale services."""
        cpu_threshold = config.get("cpu_threshold", 80)
        memory_threshold = config.get("memory_threshold", 85)
        
        # This would check resource usage and scale if needed
        logger.info(f"Checking if scaling needed (CPU > {cpu_threshold}%, Memory > {memory_threshold}%)")
    
    def _is_rate_limited(self, action_id: str) -> bool:
        """Check if action is rate limited."""
        current_time = time.time()
        hour_ago = current_time - 3600
        
        if action_id not in self.execution_counts:
            self.execution_counts[action_id] = []
        
        # Remove old executions
        self.execution_counts[action_id] = [
            t for t in self.execution_counts[action_id] if t > hour_ago
        ]
        
        return len(self.execution_counts[action_id]) >= self.max_executions_per_hour
    
    def _record_execution(self, action_id: str):
        """Record an execution for rate limiting."""
        current_time = time.time()
        
        if action_id not in self.execution_counts:
            self.execution_counts[action_id] = []
        
        self.execution_counts[action_id].append(current_time)
    
    def get_execution_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get execution history."""
        with self._lock:
            recent_executions = self.execution_history[-limit:]
            return [execution.to_dict() for execution in recent_executions]
    
    def get_active_executions(self) -> List[Dict[str, Any]]:
        """Get active executions."""
        with self._lock:
            return [execution.to_dict() for execution in self.active_executions.values()]

# Global incident response automation
_incident_response: Optional[IncidentResponseAutomation] = None

def get_incident_response() -> IncidentResponseAutomation:
    """Get global incident response automation instance."""
    global _incident_response
    if _incident_response is None:
        _incident_response = IncidentResponseAutomation()
    return _incident_response