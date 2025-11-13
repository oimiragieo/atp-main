#!/usr/bin/env python3
"""GAP-271: DP Telemetry Exporter

Exports differentially private telemetry data while ensuring privacy budget compliance.
Supports multiple export formats and enforces epsilon budget constraints.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from metrics import DP_EVENTS_EXPORTED_TOTAL

logger = logging.getLogger(__name__)


class ExportFormat(Enum):
    """Supported export formats for DP telemetry."""

    JSON = "json"
    CSV = "csv"
    PROMETHEUS = "prometheus"


@dataclass
class DpTelemetryEvent:
    """A differentially private telemetry event."""

    event_id: str
    event_type: str
    tenant_id: str
    timestamp: datetime
    dp_value: float
    epsilon_used: float
    sensitivity: float
    raw_value: float | None = None  # For debugging only, not exported
    metadata: dict[str, Any] | None = None

    def to_dict(self, include_raw: bool = False) -> dict[str, Any]:
        """Convert event to dictionary for export."""
        result = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "tenant_id": self.tenant_id,
            "timestamp": self.timestamp.isoformat(),
            "dp_value": self.dp_value,
            "epsilon_used": self.epsilon_used,
            "sensitivity": self.sensitivity,
        }

        if include_raw and self.raw_value is not None:
            result["raw_value"] = self.raw_value

        if self.metadata:
            result["metadata"] = self.metadata

        return result


class DpTelemetryExporter:
    """Exports differentially private telemetry data with budget compliance."""

    def __init__(self, export_path: str = "./dp_telemetry", max_epsilon_per_tenant: float = 1.0):
        self.export_path = Path(export_path)
        self.export_path.mkdir(exist_ok=True)
        self.max_epsilon_per_tenant = max_epsilon_per_tenant
        self.tenant_epsilon_usage: dict[str, float] = {}
        self.pending_events: list[DpTelemetryEvent] = []

    def add_event(self, event: DpTelemetryEvent) -> bool:
        """Add a DP event for export, checking budget compliance."""
        current_usage = self.tenant_epsilon_usage.get(event.tenant_id, 0.0)

        if current_usage + event.epsilon_used > self.max_epsilon_per_tenant:
            logger.warning(
                f"Budget exceeded for tenant {event.tenant_id}: "
                f"current={current_usage:.3f}, requested={event.epsilon_used:.3f}, "
                f"limit={self.max_epsilon_per_tenant:.3f}"
            )
            return False

        self.pending_events.append(event)
        self.tenant_epsilon_usage[event.tenant_id] = current_usage + event.epsilon_used
        return True

    def export_batch(self, format_type: ExportFormat = ExportFormat.JSON) -> str:
        """Export pending events in the specified format."""
        if not self.pending_events:
            logger.info("No events to export")
            return ""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"dp_telemetry_{timestamp}"

        if format_type == ExportFormat.JSON:
            return self._export_json(filename)
        elif format_type == ExportFormat.CSV:
            return self._export_csv(filename)
        elif format_type == ExportFormat.PROMETHEUS:
            return self._export_prometheus(filename)
        else:
            raise ValueError(f"Unsupported export format: {format_type}")

    def _export_json(self, filename: str) -> str:
        """Export events as JSON."""
        filepath = self.export_path / f"{filename}.json"

        events_data = [event.to_dict() for event in self.pending_events]

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "export_timestamp": datetime.now().isoformat(),
                    "total_events": len(events_data),
                    "events": events_data,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        logger.info(f"Exported {len(self.pending_events)} events to {filepath}")
        DP_EVENTS_EXPORTED_TOTAL.inc(len(self.pending_events))

        # Clear pending events after successful export
        self.pending_events.clear()
        return str(filepath)

    def _export_csv(self, filename: str) -> str:
        """Export events as CSV."""
        import csv

        filepath = self.export_path / f"{filename}.csv"

        if not self.pending_events:
            return str(filepath)

        # Get all possible fieldnames from events
        fieldnames = set()
        for event in self.pending_events:
            fieldnames.update(event.to_dict().keys())

        fieldnames = sorted(fieldnames)  # Ensure consistent ordering

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for event in self.pending_events:
                writer.writerow(event.to_dict())

        logger.info(f"Exported {len(self.pending_events)} events to {filepath}")
        DP_EVENTS_EXPORTED_TOTAL.inc(len(self.pending_events))

        self.pending_events.clear()
        return str(filepath)

    def _export_prometheus(self, filename: str) -> str:
        """Export events in Prometheus format."""
        filepath = self.export_path / f"{filename}.prom"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# DP Telemetry Export\n")
            f.write(f"# Generated at {datetime.now().isoformat()}\n\n")

            for event in self.pending_events:
                # Write metric for each event type
                metric_name = f"dp_telemetry_{event.event_type.lower()}"
                f.write(f"# TYPE {metric_name} gauge\n")
                f.write(f"{metric_name}{{")
                f.write(f'tenant_id="{event.tenant_id}",')
                f.write(f'event_id="{event.event_id}",')
                f.write(f'sensitivity="{event.sensitivity}",')
                f.write(f'epsilon_used="{event.epsilon_used}"')
                f.write(f"}} {event.dp_value} {int(event.timestamp.timestamp())}\n\n")

        logger.info(f"Exported {len(self.pending_events)} events to {filepath}")
        DP_EVENTS_EXPORTED_TOTAL.inc(len(self.pending_events))

        self.pending_events.clear()
        return str(filepath)

    def get_budget_status(self, tenant_id: str) -> dict[str, float]:
        """Get privacy budget status for a tenant."""
        used = self.tenant_epsilon_usage.get(tenant_id, 0.0)
        remaining = max(0.0, self.max_epsilon_per_tenant - used)

        return {
            "tenant_id": tenant_id,
            "epsilon_used": used,
            "epsilon_remaining": remaining,
            "epsilon_limit": self.max_epsilon_per_tenant,
            "utilization_rate": used / self.max_epsilon_per_tenant if self.max_epsilon_per_tenant > 0 else 0.0,
        }

    def reset_budget(self, tenant_id: str):
        """Reset privacy budget for a tenant (admin operation)."""
        if tenant_id in self.tenant_epsilon_usage:
            del self.tenant_epsilon_usage[tenant_id]
            logger.info(f"Reset privacy budget for tenant {tenant_id}")


# Global exporter instance
_dp_exporter: DpTelemetryExporter | None = None


def get_dp_telemetry_exporter() -> DpTelemetryExporter | None:
    """Get the global DP telemetry exporter instance."""
    return _dp_exporter


def initialize_dp_telemetry_exporter(
    export_path: str = "./dp_telemetry", max_epsilon_per_tenant: float = 1.0
) -> DpTelemetryExporter:
    """Initialize the global DP telemetry exporter."""
    global _dp_exporter
    _dp_exporter = DpTelemetryExporter(export_path, max_epsilon_per_tenant)
    return _dp_exporter
