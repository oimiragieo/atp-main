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
Enterprise Metrics Collection
Enhanced metrics system for production monitoring with SLO tracking and AI-specific operations.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum
import threading
import json

from .registry import REGISTRY

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SLOStatus(Enum):
    """SLO status enumeration."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"

@dataclass
class SLOTarget:
    """Service Level Objective target definition."""
    name: str
    description: str
    target_percentage: float  # e.g., 99.9 for 99.9%
    measurement_window: int   # seconds
    error_budget_window: int  # seconds
    alert_threshold: float    # percentage when to alert
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class SLOMetrics:
    """SLO metrics and status."""
    target: SLOTarget
    current_percentage: float
    error_budget_remaining: float
    error_budget_consumed: float
    status: SLOStatus
    last_updated: float
    violations_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["target"] = self.target.to_dict()
        result["status"] = self.status.value
        return result

@dataclass
class AlertRule:
    """Alert rule definition."""
    name: str
    description: str
    metric_name: str
    condition: str  # e.g., "> 0.95", "< 100"
    severity: AlertSeverity
    duration: int  # seconds
    enabled: bool = True
    labels: Dict[str, str] = None
    
    def __post_init__(self):
        if self.labels is None:
            self.labels = {}
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["severity"] = self.severity.value
        return result

class EnterpriseMetricsCollector:
    """Enhanced metrics collector for enterprise monitoring."""
    
    def __init__(self):
        self.slo_targets: Dict[str, SLOTarget] = {}
        self.slo_metrics: Dict[str, SLOMetrics] = {}
        self.alert_rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, Dict[str, Any]] = {}
        
        # Metrics for AI-specific operations
        self._initialize_ai_metrics()
        
        # SLO tracking
        self._initialize_slo_targets()
        
        # Alert rules
        self._initialize_alert_rules()
        
        # Background tasks
        self._monitoring_task = None
        self._lock = threading.Lock()
    
    def _initialize_ai_metrics(self):
        """Initialize AI-specific metrics."""
        # Model routing metrics
        self.model_routing_decisions = REGISTRY.counter("atp_model_routing_decisions_total")
        self.model_routing_latency = REGISTRY.histogram(
            "atp_model_routing_latency_seconds",
            [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        )
        self.model_selection_accuracy = REGISTRY.histogram(
            "atp_model_selection_accuracy",
            [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99, 1.0]
        )
        
        # Provider health metrics
        self.provider_health_score = REGISTRY.gauge("atp_provider_health_score")
        self.provider_response_time = REGISTRY.histogram(
            "atp_provider_response_time_seconds",
            [0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
        )
        self.provider_error_rate = REGISTRY.gauge("atp_provider_error_rate")
        
        # Cost optimization metrics
        self.cost_savings_total = REGISTRY.counter("atp_cost_savings_total_usd")
        self.cost_per_request = REGISTRY.histogram(
            "atp_cost_per_request_usd",
            [0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
        )
        self.budget_utilization = REGISTRY.gauge("atp_budget_utilization_percentage")
        
        # Quality metrics
        self.response_quality_score = REGISTRY.histogram(
            "atp_response_quality_score",
            [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        )
        self.user_satisfaction_score = REGISTRY.histogram(
            "atp_user_satisfaction_score",
            [1.0, 2.0, 3.0, 4.0, 5.0]
        )
        
        # Security metrics
        self.security_violations = REGISTRY.counter("atp_security_violations_total")
        self.pii_detections = REGISTRY.counter("atp_pii_detections_total")
        self.policy_violations = REGISTRY.counter("atp_policy_violations_total")
        
        # System performance metrics
        self.request_queue_size = REGISTRY.gauge("atp_request_queue_size")
        self.active_connections = REGISTRY.gauge("atp_active_connections")
        self.memory_usage_bytes = REGISTRY.gauge("atp_memory_usage_bytes")
        self.cpu_usage_percentage = REGISTRY.gauge("atp_cpu_usage_percentage")
        
        # Business metrics
        self.revenue_per_request = REGISTRY.histogram(
            "atp_revenue_per_request_usd",
            [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0]
        )
        self.customer_tier_distribution = REGISTRY.counter("atp_customer_tier_distribution")
        self.feature_usage = REGISTRY.counter("atp_feature_usage_total")
    
    def _initialize_slo_targets(self):
        """Initialize default SLO targets."""
        slo_targets = [
            SLOTarget(
                name="availability",
                description="System availability",
                target_percentage=99.9,
                measurement_window=3600,  # 1 hour
                error_budget_window=86400,  # 24 hours
                alert_threshold=99.5
            ),
            SLOTarget(
                name="latency_p95",
                description="95th percentile response latency",
                target_percentage=95.0,  # 95% of requests under threshold
                measurement_window=300,   # 5 minutes
                error_budget_window=3600, # 1 hour
                alert_threshold=90.0
            ),
            SLOTarget(
                name="error_rate",
                description="Error rate",
                target_percentage=99.0,   # 99% success rate
                measurement_window=300,   # 5 minutes
                error_budget_window=3600, # 1 hour
                alert_threshold=95.0
            ),
            SLOTarget(
                name="cost_efficiency",
                description="Cost per successful request",
                target_percentage=95.0,   # 95% within budget
                measurement_window=3600,  # 1 hour
                error_budget_window=86400, # 24 hours
                alert_threshold=90.0
            )
        ]
        
        for target in slo_targets:
            self.slo_targets[target.name] = target
            self.slo_metrics[target.name] = SLOMetrics(
                target=target,
                current_percentage=100.0,
                error_budget_remaining=100.0,
                error_budget_consumed=0.0,
                status=SLOStatus.HEALTHY,
                last_updated=time.time(),
                violations_count=0
            )
    
    def _initialize_alert_rules(self):
        """Initialize default alert rules."""
        alert_rules = [
            AlertRule(
                name="high_error_rate",
                description="High error rate detected",
                metric_name="atp_requests_total",
                condition="> 0.05",  # 5% error rate
                severity=AlertSeverity.CRITICAL,
                duration=300,  # 5 minutes
                labels={"team": "platform", "service": "atp"}
            ),
            AlertRule(
                name="high_latency",
                description="High response latency",
                metric_name="atp_request_duration_seconds",
                condition="> 5.0",  # 5 seconds
                severity=AlertSeverity.WARNING,
                duration=300,
                labels={"team": "platform", "service": "atp"}
            ),
            AlertRule(
                name="low_availability",
                description="System availability below threshold",
                metric_name="atp_availability_percentage",
                condition="< 99.5",
                severity=AlertSeverity.CRITICAL,
                duration=60,
                labels={"team": "platform", "service": "atp", "priority": "high"}
            ),
            AlertRule(
                name="budget_exceeded",
                description="Cost budget exceeded",
                metric_name="atp_budget_utilization_percentage",
                condition="> 90.0",
                severity=AlertSeverity.WARNING,
                duration=300,
                labels={"team": "finance", "service": "atp"}
            ),
            AlertRule(
                name="provider_unhealthy",
                description="Provider health score low",
                metric_name="atp_provider_health_score",
                condition="< 0.7",
                severity=AlertSeverity.WARNING,
                duration=600,  # 10 minutes
                labels={"team": "platform", "service": "atp"}
            ),
            AlertRule(
                name="security_violations",
                description="Security violations detected",
                metric_name="atp_security_violations_total",
                condition="> 0",
                severity=AlertSeverity.CRITICAL,
                duration=0,  # Immediate
                labels={"team": "security", "service": "atp", "priority": "high"}
            )
        ]
        
        for rule in alert_rules:
            self.alert_rules[rule.name] = rule
    
    def record_model_routing_decision(
        self, 
        model_name: str, 
        provider: str, 
        latency: float,
        cost: float,
        quality_score: Optional[float] = None
    ):
        """Record a model routing decision."""
        self.model_routing_decisions.inc(1)
        self.model_routing_latency.observe(latency)
        self.cost_per_request.observe(cost)
        
        if quality_score is not None:
            self.response_quality_score.observe(quality_score)
        
        # Update provider-specific metrics
        # In a real implementation, these would be labeled metrics
        logger.debug(f"Recorded routing decision: {model_name} via {provider}")
    
    def record_provider_health(
        self, 
        provider: str, 
        health_score: float, 
        response_time: float,
        error_rate: float
    ):
        """Record provider health metrics."""
        self.provider_health_score.set(health_score)
        self.provider_response_time.observe(response_time)
        self.provider_error_rate.set(error_rate)
        
        logger.debug(f"Recorded provider health: {provider} = {health_score}")
    
    def record_cost_savings(self, amount: float):
        """Record cost savings."""
        self.cost_savings_total.inc(amount)
    
    def record_security_violation(self, violation_type: str, severity: str):
        """Record a security violation."""
        self.security_violations.inc(1)
        
        # Trigger immediate alert for security violations
        self._trigger_alert("security_violations", {
            "type": violation_type,
            "severity": severity,
            "timestamp": time.time()
        })
    
    def record_pii_detection(self, pii_type: str, action: str):
        """Record PII detection."""
        self.pii_detections.inc(1)
        logger.info(f"PII detected: {pii_type}, action: {action}")
    
    def record_user_satisfaction(self, score: float):
        """Record user satisfaction score."""
        self.user_satisfaction_score.observe(score)
    
    def update_system_metrics(
        self, 
        queue_size: int, 
        active_connections: int,
        memory_bytes: int, 
        cpu_percentage: float
    ):
        """Update system performance metrics."""
        self.request_queue_size.set(queue_size)
        self.active_connections.set(active_connections)
        self.memory_usage_bytes.set(memory_bytes)
        self.cpu_usage_percentage.set(cpu_percentage)
    
    def update_budget_utilization(self, percentage: float):
        """Update budget utilization."""
        self.budget_utilization.set(percentage)
        
        # Check for budget alerts
        if percentage > 90.0:
            self._trigger_alert("budget_exceeded", {
                "utilization": percentage,
                "timestamp": time.time()
            })
    
    def calculate_slo_metrics(self):
        """Calculate current SLO metrics."""
        current_time = time.time()
        
        for slo_name, target in self.slo_targets.items():
            try:
                # Get current metrics for SLO calculation
                current_percentage = self._calculate_slo_percentage(target)
                error_budget_consumed = max(0, 100.0 - current_percentage)
                error_budget_remaining = max(0, 100.0 - error_budget_consumed)
                
                # Determine status
                if current_percentage >= target.target_percentage:
                    status = SLOStatus.HEALTHY
                elif current_percentage >= target.alert_threshold:
                    status = SLOStatus.WARNING
                else:
                    status = SLOStatus.CRITICAL
                
                # Update SLO metrics
                old_metrics = self.slo_metrics[slo_name]
                violations_count = old_metrics.violations_count
                
                if status == SLOStatus.CRITICAL:
                    violations_count += 1
                
                self.slo_metrics[slo_name] = SLOMetrics(
                    target=target,
                    current_percentage=current_percentage,
                    error_budget_remaining=error_budget_remaining,
                    error_budget_consumed=error_budget_consumed,
                    status=status,
                    last_updated=current_time,
                    violations_count=violations_count
                )
                
                # Trigger alerts if needed
                if status == SLOStatus.CRITICAL:
                    self._trigger_slo_alert(slo_name, current_percentage, target)
                
            except Exception as e:
                logger.error(f"Error calculating SLO metrics for {slo_name}: {e}")
    
    def _calculate_slo_percentage(self, target: SLOTarget) -> float:
        """Calculate current SLO percentage."""
        # This is a simplified calculation
        # In practice, you'd query your metrics backend for actual values
        
        if target.name == "availability":
            # Calculate availability based on successful requests
            total_requests = sum(c.value for c in REGISTRY.counters.values() if "requests_total" in c.__class__.__name__)
            if total_requests == 0:
                return 100.0
            
            error_requests = sum(c.value for c in REGISTRY.counters.values() if "errors_total" in c.__class__.__name__)
            success_rate = ((total_requests - error_requests) / total_requests) * 100
            return min(100.0, success_rate)
        
        elif target.name == "latency_p95":
            # Simplified latency calculation
            return 95.0  # Placeholder
        
        elif target.name == "error_rate":
            # Calculate error rate
            total_requests = sum(c.value for c in REGISTRY.counters.values() if "requests_total" in c.__class__.__name__)
            if total_requests == 0:
                return 100.0
            
            error_requests = sum(c.value for c in REGISTRY.counters.values() if "errors_total" in c.__class__.__name__)
            success_rate = ((total_requests - error_requests) / total_requests) * 100
            return min(100.0, success_rate)
        
        elif target.name == "cost_efficiency":
            # Calculate cost efficiency
            budget_util = self.budget_utilization.value
            return max(0.0, 100.0 - budget_util)
        
        return 100.0  # Default
    
    def _trigger_alert(self, alert_name: str, context: Dict[str, Any]):
        """Trigger an alert."""
        alert_id = f"{alert_name}_{int(time.time())}"
        
        alert = {
            "id": alert_id,
            "name": alert_name,
            "timestamp": time.time(),
            "status": "firing",
            "context": context
        }
        
        if alert_name in self.alert_rules:
            rule = self.alert_rules[alert_name]
            alert.update({
                "description": rule.description,
                "severity": rule.severity.value,
                "labels": rule.labels
            })
        
        self.active_alerts[alert_id] = alert
        logger.warning(f"Alert triggered: {alert_name} - {context}")
    
    def _trigger_slo_alert(self, slo_name: str, current_percentage: float, target: SLOTarget):
        """Trigger SLO violation alert."""
        self._trigger_alert(f"slo_violation_{slo_name}", {
            "slo_name": slo_name,
            "current_percentage": current_percentage,
            "target_percentage": target.target_percentage,
            "error_budget_consumed": 100.0 - current_percentage
        })
    
    def get_slo_status(self) -> Dict[str, Any]:
        """Get current SLO status."""
        return {
            "slos": {name: metrics.to_dict() for name, metrics in self.slo_metrics.items()},
            "overall_status": self._get_overall_slo_status(),
            "last_updated": time.time()
        }
    
    def _get_overall_slo_status(self) -> str:
        """Get overall SLO status."""
        statuses = [metrics.status for metrics in self.slo_metrics.values()]
        
        if any(status == SLOStatus.CRITICAL for status in statuses):
            return SLOStatus.CRITICAL.value
        elif any(status == SLOStatus.WARNING for status in statuses):
            return SLOStatus.WARNING.value
        else:
            return SLOStatus.HEALTHY.value
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get active alerts."""
        return list(self.active_alerts.values())
    
    def resolve_alert(self, alert_id: str):
        """Resolve an alert."""
        if alert_id in self.active_alerts:
            self.active_alerts[alert_id]["status"] = "resolved"
            self.active_alerts[alert_id]["resolved_at"] = time.time()
            logger.info(f"Alert resolved: {alert_id}")
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary."""
        return {
            "slo_status": self.get_slo_status(),
            "active_alerts": self.get_active_alerts(),
            "system_metrics": {
                "request_queue_size": self.request_queue_size.value,
                "active_connections": self.active_connections.value,
                "memory_usage_bytes": self.memory_usage_bytes.value,
                "cpu_usage_percentage": self.cpu_usage_percentage.value,
                "budget_utilization": self.budget_utilization.value
            },
            "ai_metrics": {
                "model_routing_decisions": self.model_routing_decisions.value,
                "cost_savings_total": self.cost_savings_total.value,
                "security_violations": self.security_violations.value,
                "pii_detections": self.pii_detections.value
            },
            "timestamp": time.time()
        }
    
    async def start_monitoring(self):
        """Start background monitoring tasks."""
        if self._monitoring_task is None:
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
            logger.info("Started enterprise metrics monitoring")
    
    async def stop_monitoring(self):
        """Stop background monitoring tasks."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
            logger.info("Stopped enterprise metrics monitoring")
    
    async def _monitoring_loop(self):
        """Background monitoring loop."""
        while True:
            try:
                # Calculate SLO metrics every minute
                self.calculate_slo_metrics()
                
                # Clean up old resolved alerts (older than 24 hours)
                current_time = time.time()
                old_alerts = [
                    alert_id for alert_id, alert in self.active_alerts.items()
                    if alert.get("status") == "resolved" and 
                       current_time - alert.get("resolved_at", 0) > 86400
                ]
                
                for alert_id in old_alerts:
                    del self.active_alerts[alert_id]
                
                await asyncio.sleep(60)  # Run every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)

# Global enterprise metrics collector
ENTERPRISE_METRICS = EnterpriseMetricsCollector()