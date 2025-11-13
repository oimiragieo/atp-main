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
Vertex AI Model Monitoring

This module provides comprehensive model monitoring and performance tracking
for Vertex AI models deployed through the ATP platform.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from google.cloud import aiplatform
from google.cloud.monitoring_v3 import AlertPolicyServiceClient, MetricServiceClient
from google.cloud.monitoring_v3.types import Metric, MetricDescriptor, TimeSeries

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MonitoringMetric(Enum):
    """Monitoring metrics."""

    REQUEST_COUNT = "request_count"
    ERROR_RATE = "error_rate"
    LATENCY_P50 = "latency_p50"
    LATENCY_P95 = "latency_p95"
    LATENCY_P99 = "latency_p99"
    CPU_UTILIZATION = "cpu_utilization"
    MEMORY_UTILIZATION = "memory_utilization"
    PREDICTION_DRIFT = "prediction_drift"
    DATA_DRIFT = "data_drift"
    MODEL_ACCURACY = "model_accuracy"


@dataclass
class MonitoringConfig:
    """Model monitoring configuration."""

    model_id: str
    endpoint_id: str
    enabled_metrics: list[MonitoringMetric]
    sampling_rate: float = 1.0
    alert_thresholds: dict[str, float] = None
    notification_channels: list[str] = None
    monitoring_interval_minutes: int = 5
    data_drift_detection: bool = True
    prediction_drift_detection: bool = True

    def __post_init__(self):
        if self.alert_thresholds is None:
            self.alert_thresholds = {}
        if self.notification_channels is None:
            self.notification_channels = []

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["enabled_metrics"] = [m.value for m in self.enabled_metrics]
        return result


@dataclass
class MonitoringAlert:
    """Monitoring alert."""

    alert_id: str
    model_id: str
    metric: MonitoringMetric
    severity: AlertSeverity
    threshold: float
    current_value: float
    message: str
    created_at: float
    resolved_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["metric"] = self.metric.value
        result["severity"] = self.severity.value
        return result


@dataclass
class ModelPerformanceMetrics:
    """Model performance metrics."""

    model_id: str
    endpoint_id: str
    timestamp: float
    request_count: int
    error_count: int
    error_rate: float
    latency_p50: float
    latency_p95: float
    latency_p99: float
    cpu_utilization: float
    memory_utilization: float
    prediction_drift_score: float | None = None
    data_drift_score: float | None = None
    accuracy_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class VertexAIMonitoring:
    """Vertex AI model monitoring system."""

    def __init__(self, project_id: str, location: str = "us-central1"):
        self.project_id = project_id
        self.location = location

        # Initialize clients
        self.monitoring_client = MetricServiceClient()
        self.alert_client = AlertPolicyServiceClient()

        # Initialize AI Platform
        aiplatform.init(project=project_id, location=location)

        # State tracking
        self.monitoring_configs: dict[str, MonitoringConfig] = {}
        self.active_alerts: dict[str, MonitoringAlert] = {}
        self.performance_history: dict[str, list[ModelPerformanceMetrics]] = {}
        self.alert_callbacks: list[Callable] = []

        # Monitoring control
        self.monitoring_active = False
        self.monitor_task = None

    async def start_monitoring(self):
        """Start model monitoring."""
        if self.monitoring_active:
            return

        self.monitoring_active = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Started Vertex AI model monitoring")

    async def stop_monitoring(self):
        """Stop model monitoring."""
        self.monitoring_active = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped Vertex AI model monitoring")

    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.monitoring_active:
            try:
                await self._collect_metrics()
                await self._check_alerts()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)

    async def _collect_metrics(self):
        """Collect metrics for all monitored models."""
        for model_id, config in self.monitoring_configs.items():
            try:
                metrics = await self._collect_model_metrics(config)
                if metrics:
                    # Store metrics
                    if model_id not in self.performance_history:
                        self.performance_history[model_id] = []

                    self.performance_history[model_id].append(metrics)

                    # Keep only last 1000 metrics per model
                    if len(self.performance_history[model_id]) > 1000:
                        self.performance_history[model_id] = self.performance_history[model_id][-1000:]

            except Exception as e:
                logger.error(f"Failed to collect metrics for model {model_id}: {e}")

    async def _collect_model_metrics(self, config: MonitoringConfig) -> ModelPerformanceMetrics | None:
        """Collect metrics for a specific model."""
        try:
            # Query Cloud Monitoring for metrics
            project_name = f"projects/{self.project_id}"

            # Define time range (last 5 minutes)
            end_time = time.time()
            start_time = end_time - (config.monitoring_interval_minutes * 60)

            interval = {"end_time": {"seconds": int(end_time)}, "start_time": {"seconds": int(start_time)}}

            # Collect different metrics
            metrics_data = {}

            for metric in config.enabled_metrics:
                if metric == MonitoringMetric.REQUEST_COUNT:
                    metrics_data["request_count"] = await self._query_metric(
                        project_name,
                        "aiplatform.googleapis.com/prediction/online/request_count",
                        config.endpoint_id,
                        interval,
                    )

                elif metric == MonitoringMetric.ERROR_RATE:
                    error_count = await self._query_metric(
                        project_name,
                        "aiplatform.googleapis.com/prediction/online/error_count",
                        config.endpoint_id,
                        interval,
                    )
                    request_count = metrics_data.get("request_count", 1)
                    metrics_data["error_rate"] = error_count / request_count if request_count > 0 else 0
                    metrics_data["error_count"] = error_count

                elif metric == MonitoringMetric.LATENCY_P95:
                    metrics_data["latency_p95"] = await self._query_percentile_metric(
                        project_name,
                        "aiplatform.googleapis.com/prediction/online/response_latencies",
                        config.endpoint_id,
                        interval,
                        95,
                    )

                elif metric == MonitoringMetric.CPU_UTILIZATION:
                    metrics_data["cpu_utilization"] = await self._query_metric(
                        project_name,
                        "aiplatform.googleapis.com/prediction/online/cpu_utilization",
                        config.endpoint_id,
                        interval,
                    )

                elif metric == MonitoringMetric.MEMORY_UTILIZATION:
                    metrics_data["memory_utilization"] = await self._query_metric(
                        project_name,
                        "aiplatform.googleapis.com/prediction/online/memory_utilization",
                        config.endpoint_id,
                        interval,
                    )

            # Create performance metrics object
            return ModelPerformanceMetrics(
                model_id=config.model_id,
                endpoint_id=config.endpoint_id,
                timestamp=time.time(),
                request_count=int(metrics_data.get("request_count", 0)),
                error_count=int(metrics_data.get("error_count", 0)),
                error_rate=metrics_data.get("error_rate", 0.0),
                latency_p50=metrics_data.get("latency_p50", 0.0),
                latency_p95=metrics_data.get("latency_p95", 0.0),
                latency_p99=metrics_data.get("latency_p99", 0.0),
                cpu_utilization=metrics_data.get("cpu_utilization", 0.0),
                memory_utilization=metrics_data.get("memory_utilization", 0.0),
                prediction_drift_score=metrics_data.get("prediction_drift_score"),
                data_drift_score=metrics_data.get("data_drift_score"),
                accuracy_score=metrics_data.get("accuracy_score"),
            )

        except Exception as e:
            logger.error(f"Failed to collect metrics for {config.model_id}: {e}")
            return None

    async def _query_metric(
        self, project_name: str, metric_type: str, resource_name: str, interval: dict[str, Any]
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

    async def _query_percentile_metric(
        self, project_name: str, metric_type: str, resource_name: str, interval: dict[str, Any], percentile: int
    ) -> float:
        """Query a percentile metric from Cloud Monitoring."""
        try:
            # This would query percentile metrics
            # Placeholder implementation
            return 0.0

        except Exception as e:
            logger.error(f"Failed to query percentile metric {metric_type}: {e}")
            return 0.0

    async def _check_alerts(self):
        """Check alert conditions for all monitored models."""
        for model_id, config in self.monitoring_configs.items():
            try:
                await self._check_model_alerts(config)
            except Exception as e:
                logger.error(f"Failed to check alerts for model {model_id}: {e}")

    async def _check_model_alerts(self, config: MonitoringConfig):
        """Check alert conditions for a specific model."""
        if config.model_id not in self.performance_history:
            return

        # Get latest metrics
        latest_metrics = self.performance_history[config.model_id][-1]

        # Check each threshold
        for metric_name, threshold in config.alert_thresholds.items():
            try:
                metric_enum = MonitoringMetric(metric_name)
                current_value = getattr(latest_metrics, metric_name, 0)

                # Determine if alert should be triggered
                should_alert = False
                severity = AlertSeverity.LOW

                if metric_name == "error_rate":
                    should_alert = current_value > threshold
                    severity = AlertSeverity.HIGH if current_value > threshold * 2 else AlertSeverity.MEDIUM

                elif metric_name in ["latency_p95", "latency_p99"]:
                    should_alert = current_value > threshold
                    severity = AlertSeverity.MEDIUM

                elif metric_name in ["cpu_utilization", "memory_utilization"]:
                    should_alert = current_value > threshold
                    severity = AlertSeverity.LOW if current_value < threshold * 1.2 else AlertSeverity.MEDIUM

                # Create or resolve alert
                alert_key = f"{config.model_id}_{metric_name}"

                if should_alert and alert_key not in self.active_alerts:
                    # Create new alert
                    alert = MonitoringAlert(
                        alert_id=f"alert_{int(time.time())}_{alert_key}",
                        model_id=config.model_id,
                        metric=metric_enum,
                        severity=severity,
                        threshold=threshold,
                        current_value=current_value,
                        message=f"Model {config.model_id} {metric_name} ({current_value:.3f}) exceeded threshold ({threshold:.3f})",
                        created_at=time.time(),
                    )

                    self.active_alerts[alert_key] = alert
                    await self._trigger_alert(alert)

                elif not should_alert and alert_key in self.active_alerts:
                    # Resolve existing alert
                    alert = self.active_alerts[alert_key]
                    alert.resolved_at = time.time()
                    await self._resolve_alert(alert)
                    del self.active_alerts[alert_key]

            except Exception as e:
                logger.error(f"Failed to check alert for {metric_name}: {e}")

    async def _trigger_alert(self, alert: MonitoringAlert):
        """Trigger an alert."""
        logger.warning(f"ALERT: {alert.message}")

        # Execute alert callbacks
        for callback in self.alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert)
                else:
                    callback(alert)
            except Exception as e:
                logger.error(f"Error executing alert callback: {e}")

    async def _resolve_alert(self, alert: MonitoringAlert):
        """Resolve an alert."""
        logger.info(f"RESOLVED: Alert {alert.alert_id} for model {alert.model_id}")

        # Execute resolution callbacks
        for callback in self.alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert)
                else:
                    callback(alert)
            except Exception as e:
                logger.error(f"Error executing alert resolution callback: {e}")

    def add_monitoring_config(self, config: MonitoringConfig):
        """Add monitoring configuration for a model."""
        self.monitoring_configs[config.model_id] = config
        logger.info(f"Added monitoring config for model {config.model_id}")

    def remove_monitoring_config(self, model_id: str):
        """Remove monitoring configuration for a model."""
        if model_id in self.monitoring_configs:
            del self.monitoring_configs[model_id]
            logger.info(f"Removed monitoring config for model {model_id}")

    def add_alert_callback(self, callback: Callable):
        """Add callback for alert notifications."""
        self.alert_callbacks.append(callback)

    async def get_model_metrics(self, model_id: str, time_range_hours: int = 24) -> list[dict[str, Any]]:
        """Get historical metrics for a model."""
        if model_id not in self.performance_history:
            return []

        # Filter metrics by time range
        cutoff_time = time.time() - (time_range_hours * 3600)
        filtered_metrics = [
            metrics.to_dict() for metrics in self.performance_history[model_id] if metrics.timestamp >= cutoff_time
        ]

        return filtered_metrics

    async def get_active_alerts(self, model_id: str | None = None) -> list[dict[str, Any]]:
        """Get active alerts."""
        alerts = []

        for alert in self.active_alerts.values():
            if model_id is None or alert.model_id == model_id:
                alerts.append(alert.to_dict())

        return alerts

    async def get_model_health_score(self, model_id: str) -> dict[str, Any]:
        """Calculate overall health score for a model."""
        if model_id not in self.performance_history:
            return {"error": f"No metrics found for model {model_id}"}

        # Get recent metrics (last hour)
        recent_metrics = [
            metrics for metrics in self.performance_history[model_id] if metrics.timestamp >= time.time() - 3600
        ]

        if not recent_metrics:
            return {"error": f"No recent metrics found for model {model_id}"}

        # Calculate health score components
        avg_error_rate = sum(m.error_rate for m in recent_metrics) / len(recent_metrics)
        avg_latency_p95 = sum(m.latency_p95 for m in recent_metrics) / len(recent_metrics)
        avg_cpu_util = sum(m.cpu_utilization for m in recent_metrics) / len(recent_metrics)
        avg_memory_util = sum(m.memory_utilization for m in recent_metrics) / len(recent_metrics)

        # Calculate health score (0-100)
        error_score = max(0, 100 - (avg_error_rate * 1000))  # Penalize errors heavily
        latency_score = max(0, 100 - (avg_latency_p95 / 10))  # Penalize high latency
        resource_score = max(0, 100 - max(avg_cpu_util, avg_memory_util))  # Penalize high resource usage

        overall_score = error_score * 0.5 + latency_score * 0.3 + resource_score * 0.2

        # Determine health status
        if overall_score >= 90:
            status = "excellent"
        elif overall_score >= 75:
            status = "good"
        elif overall_score >= 60:
            status = "fair"
        elif overall_score >= 40:
            status = "poor"
        else:
            status = "critical"

        return {
            "model_id": model_id,
            "health_score": round(overall_score, 2),
            "status": status,
            "components": {
                "error_score": round(error_score, 2),
                "latency_score": round(latency_score, 2),
                "resource_score": round(resource_score, 2),
            },
            "metrics": {
                "avg_error_rate": round(avg_error_rate, 4),
                "avg_latency_p95": round(avg_latency_p95, 2),
                "avg_cpu_utilization": round(avg_cpu_util, 2),
                "avg_memory_utilization": round(avg_memory_util, 2),
            },
            "active_alerts": len([a for a in self.active_alerts.values() if a.model_id == model_id]),
            "timestamp": time.time(),
        }

    async def create_custom_metric(self, metric_name: str, metric_description: str, metric_type: str = "GAUGE") -> bool:
        """Create a custom metric in Cloud Monitoring."""
        try:
            project_name = f"projects/{self.project_id}"

            descriptor = MetricDescriptor(
                type=f"custom.googleapis.com/atp/{metric_name}",
                metric_kind=getattr(MetricDescriptor.MetricKind, metric_type),
                value_type=MetricDescriptor.ValueType.DOUBLE,
                description=metric_description,
                display_name=metric_name,
            )

            self.monitoring_client.create_metric_descriptor(name=project_name, metric_descriptor=descriptor)

            logger.info(f"Created custom metric: {metric_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to create custom metric {metric_name}: {e}")
            return False

    async def send_custom_metric(self, metric_name: str, value: float, labels: dict[str, str] | None = None) -> bool:
        """Send a custom metric value."""
        try:
            project_name = f"projects/{self.project_id}"

            series = TimeSeries(
                metric=Metric(type=f"custom.googleapis.com/atp/{metric_name}", labels=labels or {}),
                resource={"type": "global", "labels": {"project_id": self.project_id}},
                points=[{"interval": {"end_time": {"seconds": int(time.time())}}, "value": {"double_value": value}}],
            )

            self.monitoring_client.create_time_series(name=project_name, time_series=[series])

            return True

        except Exception as e:
            logger.error(f"Failed to send custom metric {metric_name}: {e}")
            return False
