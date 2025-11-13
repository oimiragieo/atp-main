"""Cost anomaly detection system with automated alerting."""

import logging
import statistics
import time
from collections import deque
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class CostAnomalyDetector:
    """Detects cost anomalies using statistical methods."""

    def __init__(self, config=None):
        self.config = config

        # Anomaly detection parameters
        self.threshold_std_dev = getattr(config, "anomaly_threshold_std_dev", 2.5)
        self.window_hours = getattr(config, "anomaly_window_hours", 24)
        self.min_requests = getattr(config, "anomaly_min_requests", 10)

        # Historical data for anomaly detection
        self._cost_data = deque(maxlen=1000)  # (timestamp, cost, metadata)
        self._usage_data = deque(maxlen=1000)  # (timestamp, tokens, metadata)

        # Anomaly tracking
        self._detected_anomalies: list[dict[str, Any]] = []
        self._anomaly_patterns: dict[str, list[float]] = {}

        # Baseline statistics
        self._baseline_stats: dict[str, Any] = {}
        self._last_baseline_update = 0.0
        self._baseline_update_interval = 3600  # 1 hour

        logger.info("Cost anomaly detector initialized")

    def add_cost_data_point(
        self,
        cost_usd: float,
        tokens: int,
        provider: str,
        model: str,
        tenant_id: str | None = None,
        timestamp: float | None = None,
    ) -> None:
        """Add a new cost data point for anomaly detection."""
        if timestamp is None:
            timestamp = time.time()

        metadata = {
            "provider": provider,
            "model": model,
            "tenant_id": tenant_id,
            "tokens": tokens,
            "cost_per_token": cost_usd / max(tokens, 1),
        }

        self._cost_data.append((timestamp, cost_usd, metadata))
        self._usage_data.append((timestamp, tokens, metadata))

        # Update baseline statistics periodically
        if timestamp - self._last_baseline_update > self._baseline_update_interval:
            self._update_baseline_statistics()
            self._last_baseline_update = timestamp

    def detect_anomalies(
        self, tenant_id: str | None = None, provider: str | None = None, model: str | None = None
    ) -> list[dict[str, Any]]:
        """Detect cost anomalies in recent data."""
        current_time = time.time()
        window_start = current_time - (self.window_hours * 3600)

        # Filter data by time window and optional filters
        filtered_data = []
        for timestamp, cost, metadata in self._cost_data:
            if timestamp < window_start:
                continue

            if tenant_id and metadata.get("tenant_id") != tenant_id:
                continue

            if provider and metadata.get("provider") != provider:
                continue

            if model and metadata.get("model") != model:
                continue

            filtered_data.append((timestamp, cost, metadata))

        if len(filtered_data) < self.min_requests:
            return []

        # Detect different types of anomalies
        anomalies = []

        # 1. Statistical outliers in cost
        cost_anomalies = self._detect_cost_outliers(filtered_data)
        anomalies.extend(cost_anomalies)

        # 2. Cost per token anomalies
        cost_per_token_anomalies = self._detect_cost_per_token_anomalies(filtered_data)
        anomalies.extend(cost_per_token_anomalies)

        # 3. Usage pattern anomalies
        usage_anomalies = self._detect_usage_anomalies(filtered_data)
        anomalies.extend(usage_anomalies)

        # 4. Temporal anomalies (unusual timing patterns)
        temporal_anomalies = self._detect_temporal_anomalies(filtered_data)
        anomalies.extend(temporal_anomalies)

        # Store detected anomalies
        for anomaly in anomalies:
            anomaly["detected_at"] = current_time
            self._detected_anomalies.append(anomaly)

        # Keep only recent anomalies (last 7 days)
        week_ago = current_time - (7 * 24 * 3600)
        self._detected_anomalies = [a for a in self._detected_anomalies if a["detected_at"] > week_ago]

        return anomalies

    def _detect_cost_outliers(self, data: list[tuple[float, float, dict]]) -> list[dict[str, Any]]:
        """Detect statistical outliers in cost data."""
        if len(data) < 10:
            return []

        costs = [cost for _, cost, _ in data]
        mean_cost = statistics.mean(costs)
        std_cost = statistics.stdev(costs) if len(costs) > 1 else 0

        if std_cost == 0:
            return []

        anomalies = []
        self.threshold_std_dev * std_cost

        for timestamp, cost, metadata in data:
            z_score = abs(cost - mean_cost) / std_cost

            if z_score > self.threshold_std_dev:
                anomalies.append(
                    {
                        "type": "cost_outlier",
                        "severity": "high" if z_score > 3.0 else "medium",
                        "timestamp": timestamp,
                        "cost_usd": cost,
                        "expected_cost_usd": mean_cost,
                        "z_score": z_score,
                        "deviation_percent": ((cost - mean_cost) / mean_cost) * 100,
                        "metadata": metadata,
                        "description": f"Cost ${cost:.4f} is {z_score:.1f} standard deviations from mean ${mean_cost:.4f}",
                    }
                )

        return anomalies

    def _detect_cost_per_token_anomalies(self, data: list[tuple[float, float, dict]]) -> list[dict[str, Any]]:
        """Detect anomalies in cost per token."""
        if len(data) < 10:
            return []

        cost_per_token_values = [metadata["cost_per_token"] for _, _, metadata in data]
        mean_cpt = statistics.mean(cost_per_token_values)
        std_cpt = statistics.stdev(cost_per_token_values) if len(cost_per_token_values) > 1 else 0

        if std_cpt == 0:
            return []

        anomalies = []

        for timestamp, cost, metadata in data:
            cost_per_token = metadata["cost_per_token"]
            z_score = abs(cost_per_token - mean_cpt) / std_cpt

            if z_score > self.threshold_std_dev:
                anomalies.append(
                    {
                        "type": "cost_per_token_anomaly",
                        "severity": "high" if z_score > 3.0 else "medium",
                        "timestamp": timestamp,
                        "cost_per_token": cost_per_token,
                        "expected_cost_per_token": mean_cpt,
                        "z_score": z_score,
                        "tokens": metadata["tokens"],
                        "total_cost_usd": cost,
                        "metadata": metadata,
                        "description": f"Cost per token ${cost_per_token:.6f} is {z_score:.1f} std devs from mean ${mean_cpt:.6f}",
                    }
                )

        return anomalies

    def _detect_usage_anomalies(self, data: list[tuple[float, float, dict]]) -> list[dict[str, Any]]:
        """Detect anomalies in token usage patterns."""
        if len(data) < 10:
            return []

        token_counts = [metadata["tokens"] for _, _, metadata in data]
        mean_tokens = statistics.mean(token_counts)
        std_tokens = statistics.stdev(token_counts) if len(token_counts) > 1 else 0

        if std_tokens == 0:
            return []

        anomalies = []

        for timestamp, cost, metadata in data:
            tokens = metadata["tokens"]
            z_score = abs(tokens - mean_tokens) / std_tokens

            if z_score > self.threshold_std_dev:
                anomalies.append(
                    {
                        "type": "usage_anomaly",
                        "severity": "medium" if z_score > 3.0 else "low",
                        "timestamp": timestamp,
                        "tokens": tokens,
                        "expected_tokens": mean_tokens,
                        "z_score": z_score,
                        "cost_usd": cost,
                        "metadata": metadata,
                        "description": f"Token usage {tokens} is {z_score:.1f} std devs from mean {mean_tokens:.0f}",
                    }
                )

        return anomalies

    def _detect_temporal_anomalies(self, data: list[tuple[float, float, dict]]) -> list[dict[str, Any]]:
        """Detect anomalies in timing patterns."""
        if len(data) < 20:
            return []

        # Group by hour of day
        hourly_costs = {}
        for timestamp, cost, _metadata in data:
            hour = datetime.fromtimestamp(timestamp).hour
            if hour not in hourly_costs:
                hourly_costs[hour] = []
            hourly_costs[hour].append(cost)

        # Calculate expected cost for each hour
        hourly_means = {}
        hourly_stds = {}
        for hour, costs in hourly_costs.items():
            if len(costs) >= 3:  # Need at least 3 data points
                hourly_means[hour] = statistics.mean(costs)
                hourly_stds[hour] = statistics.stdev(costs) if len(costs) > 1 else 0

        anomalies = []

        # Check recent data points against hourly patterns
        for timestamp, cost, metadata in data[-10:]:  # Check last 10 points
            hour = datetime.fromtimestamp(timestamp).hour

            if hour in hourly_means and hourly_stds[hour] > 0:
                expected_cost = hourly_means[hour]
                std_cost = hourly_stds[hour]
                z_score = abs(cost - expected_cost) / std_cost

                if z_score > self.threshold_std_dev:
                    anomalies.append(
                        {
                            "type": "temporal_anomaly",
                            "severity": "medium",
                            "timestamp": timestamp,
                            "hour_of_day": hour,
                            "cost_usd": cost,
                            "expected_cost_for_hour": expected_cost,
                            "z_score": z_score,
                            "metadata": metadata,
                            "description": f"Cost ${cost:.4f} at hour {hour} is unusual (expected ${expected_cost:.4f})",
                        }
                    )

        return anomalies

    def _update_baseline_statistics(self) -> None:
        """Update baseline statistics for anomaly detection."""
        if len(self._cost_data) < 50:
            return

        # Calculate baseline statistics from recent data
        recent_data = list(self._cost_data)[-200:]  # Last 200 points

        costs = [cost for _, cost, _ in recent_data]
        tokens = [metadata["tokens"] for _, _, metadata in recent_data]
        cost_per_token = [metadata["cost_per_token"] for _, _, metadata in recent_data]

        self._baseline_stats = {
            "cost": {
                "mean": statistics.mean(costs),
                "std": statistics.stdev(costs) if len(costs) > 1 else 0,
                "median": statistics.median(costs),
                "min": min(costs),
                "max": max(costs),
            },
            "tokens": {
                "mean": statistics.mean(tokens),
                "std": statistics.stdev(tokens) if len(tokens) > 1 else 0,
                "median": statistics.median(tokens),
                "min": min(tokens),
                "max": max(tokens),
            },
            "cost_per_token": {
                "mean": statistics.mean(cost_per_token),
                "std": statistics.stdev(cost_per_token) if len(cost_per_token) > 1 else 0,
                "median": statistics.median(cost_per_token),
                "min": min(cost_per_token),
                "max": max(cost_per_token),
            },
            "updated_at": time.time(),
            "data_points": len(recent_data),
        }

    def get_anomaly_summary(self, hours: int = 24, tenant_id: str | None = None) -> dict[str, Any]:
        """Get summary of detected anomalies."""
        current_time = time.time()
        cutoff_time = current_time - (hours * 3600)

        # Filter anomalies by time and tenant
        filtered_anomalies = []
        for anomaly in self._detected_anomalies:
            if anomaly["detected_at"] < cutoff_time:
                continue

            if tenant_id and anomaly.get("metadata", {}).get("tenant_id") != tenant_id:
                continue

            filtered_anomalies.append(anomaly)

        # Group by type and severity
        by_type = {}
        by_severity = {"high": 0, "medium": 0, "low": 0}

        for anomaly in filtered_anomalies:
            anomaly_type = anomaly["type"]
            severity = anomaly["severity"]

            if anomaly_type not in by_type:
                by_type[anomaly_type] = 0
            by_type[anomaly_type] += 1
            by_severity[severity] += 1

        # Calculate impact
        total_anomalous_cost = sum(anomaly.get("cost_usd", 0) for anomaly in filtered_anomalies)

        return {
            "period_hours": hours,
            "total_anomalies": len(filtered_anomalies),
            "anomalies_by_type": by_type,
            "anomalies_by_severity": by_severity,
            "total_anomalous_cost_usd": total_anomalous_cost,
            "baseline_stats": self._baseline_stats,
            "recent_anomalies": filtered_anomalies[-10:],  # Last 10 anomalies
            "generated_at": current_time,
        }

    def get_anomaly_patterns(self) -> dict[str, Any]:
        """Analyze patterns in detected anomalies."""
        if not self._detected_anomalies:
            return {"error": "No anomalies detected yet"}

        # Analyze patterns
        patterns = {
            "most_common_types": {},
            "most_affected_providers": {},
            "most_affected_models": {},
            "most_affected_tenants": {},
            "hourly_distribution": {},
            "severity_trends": [],
        }

        for anomaly in self._detected_anomalies:
            # Type patterns
            anomaly_type = anomaly["type"]
            patterns["most_common_types"][anomaly_type] = patterns["most_common_types"].get(anomaly_type, 0) + 1

            # Provider patterns
            provider = anomaly.get("metadata", {}).get("provider", "unknown")
            patterns["most_affected_providers"][provider] = patterns["most_affected_providers"].get(provider, 0) + 1

            # Model patterns
            model = anomaly.get("metadata", {}).get("model", "unknown")
            patterns["most_affected_models"][model] = patterns["most_affected_models"].get(model, 0) + 1

            # Tenant patterns
            tenant = anomaly.get("metadata", {}).get("tenant_id", "unknown")
            patterns["most_affected_tenants"][tenant] = patterns["most_affected_tenants"].get(tenant, 0) + 1

            # Hourly patterns
            hour = datetime.fromtimestamp(anomaly["timestamp"]).hour
            patterns["hourly_distribution"][hour] = patterns["hourly_distribution"].get(hour, 0) + 1

        # Sort patterns by frequency
        for key in ["most_common_types", "most_affected_providers", "most_affected_models", "most_affected_tenants"]:
            patterns[key] = dict(sorted(patterns[key].items(), key=lambda x: x[1], reverse=True))

        return patterns

    def is_anomalous_request(
        self, estimated_cost: float, tokens: int, provider: str, model: str, tenant_id: str | None = None
    ) -> dict[str, Any]:
        """Check if a request would be considered anomalous before processing."""
        if not self._baseline_stats:
            return {"is_anomalous": False, "reason": "No baseline statistics available"}

        cost_per_token = estimated_cost / max(tokens, 1)

        # Check against baseline statistics
        anomaly_indicators = []

        # Cost check
        cost_stats = self._baseline_stats.get("cost", {})
        if cost_stats.get("std", 0) > 0:
            cost_z_score = abs(estimated_cost - cost_stats["mean"]) / cost_stats["std"]
            if cost_z_score > self.threshold_std_dev:
                anomaly_indicators.append(
                    {
                        "type": "cost_outlier",
                        "z_score": cost_z_score,
                        "expected": cost_stats["mean"],
                        "actual": estimated_cost,
                    }
                )

        # Token usage check
        token_stats = self._baseline_stats.get("tokens", {})
        if token_stats.get("std", 0) > 0:
            token_z_score = abs(tokens - token_stats["mean"]) / token_stats["std"]
            if token_z_score > self.threshold_std_dev:
                anomaly_indicators.append(
                    {
                        "type": "usage_outlier",
                        "z_score": token_z_score,
                        "expected": token_stats["mean"],
                        "actual": tokens,
                    }
                )

        # Cost per token check
        cpt_stats = self._baseline_stats.get("cost_per_token", {})
        if cpt_stats.get("std", 0) > 0:
            cpt_z_score = abs(cost_per_token - cpt_stats["mean"]) / cpt_stats["std"]
            if cpt_z_score > self.threshold_std_dev:
                anomaly_indicators.append(
                    {
                        "type": "cost_per_token_outlier",
                        "z_score": cpt_z_score,
                        "expected": cpt_stats["mean"],
                        "actual": cost_per_token,
                    }
                )

        is_anomalous = len(anomaly_indicators) > 0

        return {
            "is_anomalous": is_anomalous,
            "anomaly_indicators": anomaly_indicators,
            "confidence": max([ind["z_score"] for ind in anomaly_indicators]) if anomaly_indicators else 0,
            "baseline_stats": self._baseline_stats,
            "request_details": {
                "estimated_cost": estimated_cost,
                "tokens": tokens,
                "cost_per_token": cost_per_token,
                "provider": provider,
                "model": model,
                "tenant_id": tenant_id,
            },
        }
