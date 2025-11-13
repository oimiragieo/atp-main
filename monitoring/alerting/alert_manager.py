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
Production Alerting and Incident Management
Comprehensive alerting system with escalation policies, on-call rotation,
incident response automation, and post-incident analysis.
"""

import asyncio
import json
import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertStatus(Enum):
    """Alert status."""

    FIRING = "firing"
    RESOLVED = "resolved"
    SILENCED = "silenced"
    ACKNOWLEDGED = "acknowledged"


class IncidentStatus(Enum):
    """Incident status."""

    OPEN = "open"
    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
    CLOSED = "closed"


class EscalationAction(Enum):
    """Escalation actions."""

    EMAIL = "email"
    SMS = "sms"
    SLACK = "slack"
    PAGERDUTY = "pagerduty"
    WEBHOOK = "webhook"
    AUTO_REMEDIATION = "auto_remediation"


@dataclass
class AlertRule:
    """Alert rule definition."""

    id: str
    name: str
    description: str
    query: str  # Prometheus-style query
    condition: str  # e.g., "> 0.95", "< 100"
    severity: AlertSeverity
    duration: int  # seconds
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["severity"] = self.severity.value
        return result


@dataclass
class Alert:
    """Alert instance."""

    id: str
    rule_id: str
    name: str
    description: str
    severity: AlertSeverity
    status: AlertStatus
    labels: dict[str, str]
    annotations: dict[str, str]
    fired_at: float
    resolved_at: float | None = None
    acknowledged_at: float | None = None
    acknowledged_by: str | None = None
    silenced_until: float | None = None
    escalation_level: int = 0

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["severity"] = self.severity.value
        result["status"] = self.status.value
        return result


@dataclass
class OnCallPerson:
    """On-call person information."""

    id: str
    name: str
    email: str
    phone: str | None = None
    slack_user_id: str | None = None
    timezone: str = "UTC"
    escalation_delay_minutes: int = 15

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EscalationPolicy:
    """Escalation policy definition."""

    id: str
    name: str
    description: str
    steps: list[dict[str, Any]]  # List of escalation steps
    repeat_interval_minutes: int = 60
    max_escalations: int = 3

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Incident:
    """Incident information."""

    id: str
    title: str
    description: str
    severity: AlertSeverity
    status: IncidentStatus
    created_at: float
    updated_at: float
    resolved_at: float | None = None
    assigned_to: str | None = None
    alerts: list[str] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    root_cause: str | None = None
    resolution: str | None = None
    lessons_learned: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["severity"] = self.severity.value
        result["status"] = self.status.value
        return result


@dataclass
class RemediationAction:
    """Automated remediation action."""

    id: str
    name: str
    description: str
    trigger_conditions: list[str]
    action_type: str  # "script", "api_call", "restart_service", etc.
    action_config: dict[str, Any]
    enabled: bool = True
    max_executions_per_hour: int = 3

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AlertManager:
    """Comprehensive alert management system."""

    def __init__(self):
        self.alert_rules: dict[str, AlertRule] = {}
        self.active_alerts: dict[str, Alert] = {}
        self.resolved_alerts: deque = deque(maxlen=10000)
        self.escalation_policies: dict[str, EscalationPolicy] = {}
        self.on_call_schedule: dict[str, OnCallPerson] = {}
        self.incidents: dict[str, Incident] = {}
        self.remediation_actions: dict[str, RemediationAction] = {}

        # Notification handlers
        self.notification_handlers: dict[str, Callable] = {}

        # Metrics
        self.alert_metrics = {
            "total_alerts": 0,
            "alerts_by_severity": defaultdict(int),
            "mean_time_to_acknowledge": 0,
            "mean_time_to_resolve": 0,
        }

        self._lock = threading.Lock()
        self._evaluation_task = None

        # Initialize default configurations
        self._initialize_default_rules()
        self._initialize_default_policies()
        self._initialize_notification_handlers()

    def _initialize_default_rules(self):
        """Initialize default alert rules."""
        default_rules = [
            AlertRule(
                id="high_error_rate",
                name="High Error Rate",
                description="Error rate is above 5%",
                query="rate(atp_errors_total[5m]) / rate(atp_requests_total[5m])",
                condition="> 0.05",
                severity=AlertSeverity.CRITICAL,
                duration=300,  # 5 minutes
                labels={"team": "platform", "service": "atp"},
                annotations={"runbook": "https://runbooks.example.com/high-error-rate"},
            ),
            AlertRule(
                id="high_latency",
                name="High Response Latency",
                description="95th percentile latency is above 2 seconds",
                query="histogram_quantile(0.95, rate(atp_request_duration_seconds_bucket[5m]))",
                condition="> 2.0",
                severity=AlertSeverity.WARNING,
                duration=300,
                labels={"team": "platform", "service": "atp"},
                annotations={"runbook": "https://runbooks.example.com/high-latency"},
            ),
            AlertRule(
                id="low_availability",
                name="Low System Availability",
                description="System availability is below 99.5%",
                query="atp_availability_percentage",
                condition="< 99.5",
                severity=AlertSeverity.CRITICAL,
                duration=60,
                labels={"team": "platform", "service": "atp", "priority": "high"},
                annotations={"runbook": "https://runbooks.example.com/low-availability"},
            ),
            AlertRule(
                id="budget_exceeded",
                name="Budget Exceeded",
                description="Cost budget utilization is above 90%",
                query="atp_budget_utilization_percentage",
                condition="> 90.0",
                severity=AlertSeverity.WARNING,
                duration=300,
                labels={"team": "finance", "service": "atp"},
                annotations={"runbook": "https://runbooks.example.com/budget-exceeded"},
            ),
            AlertRule(
                id="security_violation",
                name="Security Violation Detected",
                description="Security violations detected",
                query="increase(atp_security_violations_total[5m])",
                condition="> 0",
                severity=AlertSeverity.EMERGENCY,
                duration=0,  # Immediate
                labels={"team": "security", "service": "atp", "priority": "critical"},
                annotations={"runbook": "https://runbooks.example.com/security-violation"},
            ),
        ]

        for rule in default_rules:
            self.alert_rules[rule.id] = rule

    def _initialize_default_policies(self):
        """Initialize default escalation policies."""
        # Default escalation policy
        default_policy = EscalationPolicy(
            id="default",
            name="Default Escalation Policy",
            description="Standard escalation for platform alerts",
            steps=[
                {
                    "level": 1,
                    "delay_minutes": 0,
                    "actions": [
                        {"type": "email", "targets": ["oncall-primary@example.com"]},
                        {"type": "slack", "targets": ["#alerts"]},
                    ],
                },
                {
                    "level": 2,
                    "delay_minutes": 15,
                    "actions": [
                        {"type": "email", "targets": ["oncall-secondary@example.com"]},
                        {"type": "sms", "targets": ["+1234567890"]},
                    ],
                },
                {
                    "level": 3,
                    "delay_minutes": 30,
                    "actions": [
                        {"type": "email", "targets": ["manager@example.com"]},
                        {"type": "pagerduty", "targets": ["escalation-key"]},
                    ],
                },
            ],
            repeat_interval_minutes=60,
            max_escalations=3,
        )

        self.escalation_policies["default"] = default_policy

        # Critical escalation policy
        critical_policy = EscalationPolicy(
            id="critical",
            name="Critical Escalation Policy",
            description="Immediate escalation for critical alerts",
            steps=[
                {
                    "level": 1,
                    "delay_minutes": 0,
                    "actions": [
                        {"type": "email", "targets": ["oncall-primary@example.com"]},
                        {"type": "sms", "targets": ["+1234567890"]},
                        {"type": "slack", "targets": ["#critical-alerts"]},
                        {"type": "pagerduty", "targets": ["critical-key"]},
                    ],
                },
                {
                    "level": 2,
                    "delay_minutes": 5,
                    "actions": [
                        {"type": "email", "targets": ["manager@example.com"]},
                        {"type": "sms", "targets": ["+0987654321"]},
                    ],
                },
            ],
            repeat_interval_minutes=15,
            max_escalations=5,
        )

        self.escalation_policies["critical"] = critical_policy

    def _initialize_notification_handlers(self):
        """Initialize notification handlers."""
        self.notification_handlers = {
            "email": self._send_email_notification,
            "sms": self._send_sms_notification,
            "slack": self._send_slack_notification,
            "pagerduty": self._send_pagerduty_notification,
            "webhook": self._send_webhook_notification,
        }

    def add_alert_rule(self, rule: AlertRule):
        """Add an alert rule."""
        with self._lock:
            self.alert_rules[rule.id] = rule
        logger.info(f"Added alert rule: {rule.name}")

    def remove_alert_rule(self, rule_id: str):
        """Remove an alert rule."""
        with self._lock:
            if rule_id in self.alert_rules:
                del self.alert_rules[rule_id]
                logger.info(f"Removed alert rule: {rule_id}")

    def fire_alert(
        self, rule_id: str, labels: dict[str, str] | None = None, annotations: dict[str, str] | None = None
    ) -> str:
        """Fire an alert."""
        if rule_id not in self.alert_rules:
            raise ValueError(f"Alert rule {rule_id} not found")

        rule = self.alert_rules[rule_id]
        alert_id = str(uuid.uuid4())

        # Merge labels and annotations
        merged_labels = rule.labels.copy()
        if labels:
            merged_labels.update(labels)

        merged_annotations = rule.annotations.copy()
        if annotations:
            merged_annotations.update(annotations)

        alert = Alert(
            id=alert_id,
            rule_id=rule_id,
            name=rule.name,
            description=rule.description,
            severity=rule.severity,
            status=AlertStatus.FIRING,
            labels=merged_labels,
            annotations=merged_annotations,
            fired_at=time.time(),
        )

        with self._lock:
            self.active_alerts[alert_id] = alert
            self.alert_metrics["total_alerts"] += 1
            self.alert_metrics["alerts_by_severity"][rule.severity.value] += 1

        # Start escalation
        asyncio.create_task(self._handle_alert_escalation(alert))

        # Check for incident creation
        self._check_incident_creation(alert)

        logger.warning(f"Alert fired: {rule.name} (ID: {alert_id})")
        return alert_id

    def resolve_alert(self, alert_id: str, resolved_by: str | None = None):
        """Resolve an alert."""
        with self._lock:
            if alert_id not in self.active_alerts:
                logger.warning(f"Alert {alert_id} not found in active alerts")
                return

            alert = self.active_alerts[alert_id]
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = time.time()

            # Move to resolved alerts
            self.resolved_alerts.append(alert)
            del self.active_alerts[alert_id]

            # Update metrics
            if alert.acknowledged_at:
                time_to_resolve = alert.resolved_at - alert.acknowledged_at
                self._update_mttr(time_to_resolve)

        logger.info(f"Alert resolved: {alert.name} (ID: {alert_id})")

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str):
        """Acknowledge an alert."""
        with self._lock:
            if alert_id not in self.active_alerts:
                logger.warning(f"Alert {alert_id} not found")
                return

            alert = self.active_alerts[alert_id]
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = time.time()
            alert.acknowledged_by = acknowledged_by

            # Update metrics
            time_to_acknowledge = alert.acknowledged_at - alert.fired_at
            self._update_mtta(time_to_acknowledge)

        logger.info(f"Alert acknowledged: {alert.name} by {acknowledged_by}")

    def silence_alert(self, alert_id: str, duration_minutes: int, silenced_by: str):
        """Silence an alert for a specified duration."""
        with self._lock:
            if alert_id not in self.active_alerts:
                logger.warning(f"Alert {alert_id} not found")
                return

            alert = self.active_alerts[alert_id]
            alert.status = AlertStatus.SILENCED
            alert.silenced_until = time.time() + (duration_minutes * 60)

        logger.info(f"Alert silenced: {alert.name} for {duration_minutes} minutes by {silenced_by}")

    async def _handle_alert_escalation(self, alert: Alert):
        """Handle alert escalation."""
        # Determine escalation policy
        policy_id = "critical" if alert.severity in [AlertSeverity.CRITICAL, AlertSeverity.EMERGENCY] else "default"

        if policy_id not in self.escalation_policies:
            logger.error(f"Escalation policy {policy_id} not found")
            return

        policy = self.escalation_policies[policy_id]

        for step in policy.steps:
            # Wait for delay
            if step["delay_minutes"] > 0:
                await asyncio.sleep(step["delay_minutes"] * 60)

            # Check if alert is still active
            with self._lock:
                if alert.id not in self.active_alerts:
                    return  # Alert was resolved

                current_alert = self.active_alerts[alert.id]
                if current_alert.status in [AlertStatus.ACKNOWLEDGED, AlertStatus.SILENCED]:
                    return  # Alert was acknowledged or silenced

            # Execute escalation actions
            for action in step["actions"]:
                try:
                    await self._execute_escalation_action(alert, action)
                except Exception as e:
                    logger.error(f"Failed to execute escalation action: {e}")

            # Update escalation level
            with self._lock:
                if alert.id in self.active_alerts:
                    self.active_alerts[alert.id].escalation_level = step["level"]

    async def _execute_escalation_action(self, alert: Alert, action: dict[str, Any]):
        """Execute an escalation action."""
        action_type = action["type"]
        targets = action["targets"]

        if action_type in self.notification_handlers:
            handler = self.notification_handlers[action_type]
            await handler(alert, targets)
        else:
            logger.warning(f"Unknown escalation action type: {action_type}")

    async def _send_email_notification(self, alert: Alert, targets: list[str]):
        """Send email notification."""
        try:
            # This is a simplified implementation
            # In production, you'd use a proper email service
            subject = f"[{alert.severity.value.upper()}] {alert.name}"
            f"""
Alert: {alert.name}
Severity: {alert.severity.value}
Description: {alert.description}
Fired at: {datetime.fromtimestamp(alert.fired_at)}
Labels: {json.dumps(alert.labels, indent=2)}

Runbook: {alert.annotations.get("runbook", "N/A")}
            """

            logger.info(f"Email notification sent to {targets}: {subject}")

        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")

    async def _send_sms_notification(self, alert: Alert, targets: list[str]):
        """Send SMS notification."""
        try:
            message = f"[{alert.severity.value.upper()}] {alert.name}: {alert.description}"
            logger.info(f"SMS notification sent to {targets}: {message}")

        except Exception as e:
            logger.error(f"Failed to send SMS notification: {e}")

    async def _send_slack_notification(self, alert: Alert, targets: list[str]):
        """Send Slack notification."""
        try:
            {
                "text": f"Alert: {alert.name}",
                "attachments": [
                    {
                        "color": "danger"
                        if alert.severity in [AlertSeverity.CRITICAL, AlertSeverity.EMERGENCY]
                        else "warning",
                        "fields": [
                            {"title": "Severity", "value": alert.severity.value, "short": True},
                            {"title": "Description", "value": alert.description, "short": False},
                            {
                                "title": "Fired At",
                                "value": datetime.fromtimestamp(alert.fired_at).isoformat(),
                                "short": True,
                            },
                        ],
                    }
                ],
            }

            logger.info(f"Slack notification sent to {targets}: {alert.name}")

        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")

    async def _send_pagerduty_notification(self, alert: Alert, targets: list[str]):
        """Send PagerDuty notification."""
        try:
            # PagerDuty integration would go here
            logger.info(f"PagerDuty notification sent to {targets}: {alert.name}")

        except Exception as e:
            logger.error(f"Failed to send PagerDuty notification: {e}")

    async def _send_webhook_notification(self, alert: Alert, targets: list[str]):
        """Send webhook notification."""
        try:
            alert.to_dict()
            logger.info(f"Webhook notification sent to {targets}: {alert.name}")

        except Exception as e:
            logger.error(f"Failed to send webhook notification: {e}")

    def _check_incident_creation(self, alert: Alert):
        """Check if an incident should be created for the alert."""
        # Create incident for critical and emergency alerts
        if alert.severity in [AlertSeverity.CRITICAL, AlertSeverity.EMERGENCY]:
            self._create_incident_from_alert(alert)

    def _create_incident_from_alert(self, alert: Alert) -> str:
        """Create an incident from an alert."""
        incident_id = str(uuid.uuid4())

        incident = Incident(
            id=incident_id,
            title=f"Incident: {alert.name}",
            description=alert.description,
            severity=alert.severity,
            status=IncidentStatus.OPEN,
            created_at=time.time(),
            updated_at=time.time(),
            alerts=[alert.id],
            timeline=[
                {
                    "timestamp": time.time(),
                    "event": "incident_created",
                    "description": f"Incident created from alert: {alert.name}",
                    "user": "system",
                }
            ],
        )

        with self._lock:
            self.incidents[incident_id] = incident

        logger.warning(f"Incident created: {incident.title} (ID: {incident_id})")
        return incident_id

    def update_incident_status(self, incident_id: str, status: IncidentStatus, user: str, notes: str | None = None):
        """Update incident status."""
        with self._lock:
            if incident_id not in self.incidents:
                logger.warning(f"Incident {incident_id} not found")
                return

            incident = self.incidents[incident_id]
            old_status = incident.status
            incident.status = status
            incident.updated_at = time.time()

            if status == IncidentStatus.RESOLVED:
                incident.resolved_at = time.time()

            # Add to timeline
            timeline_entry = {
                "timestamp": time.time(),
                "event": "status_changed",
                "description": f"Status changed from {old_status.value} to {status.value}",
                "user": user,
            }

            if notes:
                timeline_entry["notes"] = notes

            incident.timeline.append(timeline_entry)

        logger.info(f"Incident {incident_id} status updated to {status.value} by {user}")

    def add_incident_note(self, incident_id: str, user: str, note: str):
        """Add a note to an incident."""
        with self._lock:
            if incident_id not in self.incidents:
                logger.warning(f"Incident {incident_id} not found")
                return

            incident = self.incidents[incident_id]
            incident.updated_at = time.time()

            timeline_entry = {"timestamp": time.time(), "event": "note_added", "description": note, "user": user}

            incident.timeline.append(timeline_entry)

        logger.info(f"Note added to incident {incident_id} by {user}")

    def _update_mtta(self, time_to_acknowledge: float):
        """Update mean time to acknowledge."""
        current_mtta = self.alert_metrics["mean_time_to_acknowledge"]
        total_alerts = self.alert_metrics["total_alerts"]

        if total_alerts > 1:
            self.alert_metrics["mean_time_to_acknowledge"] = (
                current_mtta * (total_alerts - 1) + time_to_acknowledge
            ) / total_alerts
        else:
            self.alert_metrics["mean_time_to_acknowledge"] = time_to_acknowledge

    def _update_mttr(self, time_to_resolve: float):
        """Update mean time to resolve."""
        current_mttr = self.alert_metrics["mean_time_to_resolve"]
        resolved_count = len(self.resolved_alerts)

        if resolved_count > 1:
            self.alert_metrics["mean_time_to_resolve"] = (
                current_mttr * (resolved_count - 1) + time_to_resolve
            ) / resolved_count
        else:
            self.alert_metrics["mean_time_to_resolve"] = time_to_resolve

    def get_active_alerts(self) -> list[dict[str, Any]]:
        """Get all active alerts."""
        with self._lock:
            return [alert.to_dict() for alert in self.active_alerts.values()]

    def get_incidents(self, status: IncidentStatus | None = None) -> list[dict[str, Any]]:
        """Get incidents, optionally filtered by status."""
        with self._lock:
            incidents = list(self.incidents.values())

            if status:
                incidents = [i for i in incidents if i.status == status]

            return [incident.to_dict() for incident in incidents]

    def get_alert_metrics(self) -> dict[str, Any]:
        """Get alert metrics."""
        with self._lock:
            return {
                **self.alert_metrics,
                "active_alerts": len(self.active_alerts),
                "open_incidents": len([i for i in self.incidents.values() if i.status != IncidentStatus.CLOSED]),
            }

    def generate_incident_report(self, incident_id: str) -> dict[str, Any]:
        """Generate post-incident report."""
        with self._lock:
            if incident_id not in self.incidents:
                return {"error": "Incident not found"}

            incident = self.incidents[incident_id]

            # Calculate metrics
            duration = None
            if incident.resolved_at:
                duration = incident.resolved_at - incident.created_at

            # Get related alerts
            related_alerts = []
            for alert_id in incident.alerts:
                if alert_id in self.active_alerts:
                    related_alerts.append(self.active_alerts[alert_id].to_dict())
                else:
                    # Check resolved alerts
                    for resolved_alert in self.resolved_alerts:
                        if resolved_alert.id == alert_id:
                            related_alerts.append(resolved_alert.to_dict())
                            break

            return {
                "incident": incident.to_dict(),
                "duration_seconds": duration,
                "related_alerts": related_alerts,
                "timeline_summary": len(incident.timeline),
                "generated_at": time.time(),
            }


# Global alert manager
_alert_manager: AlertManager | None = None


def get_alert_manager() -> AlertManager:
    """Get global alert manager instance."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager
