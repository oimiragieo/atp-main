"""Configuration for the cost optimization engine."""

import os
from dataclasses import dataclass


@dataclass
class OptimizationConfig:
    """Configuration for cost optimization engine."""

    # General Configuration
    enabled: bool = True
    optimization_interval_seconds: int = 300  # 5 minutes

    # Budget Management
    budget_enforcement_enabled: bool = True
    default_monthly_budget_usd: float = 1000.0
    budget_warning_threshold_percent: float = 80.0  # Warn at 80%
    budget_critical_threshold_percent: float = 95.0  # Critical at 95%
    budget_enforcement_action: str = "throttle"  # "block", "throttle", "alert"

    # Forecasting Configuration
    forecasting_enabled: bool = True
    forecasting_horizon_days: int = 30
    forecasting_confidence_interval: float = 0.95
    forecasting_min_data_points: int = 100
    forecasting_model_type: str = "linear"  # "linear", "exponential", "seasonal"

    # Anomaly Detection
    anomaly_detection_enabled: bool = True
    anomaly_threshold_std_dev: float = 2.5  # Standard deviations for anomaly
    anomaly_window_hours: int = 24
    anomaly_min_requests: int = 10  # Minimum requests to detect anomalies

    # Cost Optimization
    optimization_target: str = "cost"  # "cost", "quality", "balanced"
    cost_savings_threshold_percent: float = 10.0  # Minimum savings to recommend
    quality_degradation_tolerance: float = 0.05  # Max quality loss (5%)

    # Tenant and Project Limits
    per_tenant_budgets: dict[str, float] = None
    per_project_budgets: dict[str, float] = None
    tenant_rate_limits: dict[str, int] = None  # requests per hour

    # Alert Configuration
    alerts_enabled: bool = True
    alert_channels: list[str] = None
    alert_webhook_url: str | None = None

    # Cache Configuration
    cache_optimization_results: bool = True
    cache_ttl_seconds: int = 300

    @classmethod
    def from_environment(cls) -> "OptimizationConfig":
        """Create configuration from environment variables."""
        return cls(
            # General
            enabled=os.getenv("COST_OPTIMIZATION_ENABLED", "true").lower() == "true",
            optimization_interval_seconds=int(os.getenv("COST_OPTIMIZATION_INTERVAL", "300")),
            # Budget Management
            budget_enforcement_enabled=os.getenv("BUDGET_ENFORCEMENT_ENABLED", "true").lower() == "true",
            default_monthly_budget_usd=float(os.getenv("DEFAULT_MONTHLY_BUDGET", "1000.0")),
            budget_warning_threshold_percent=float(os.getenv("BUDGET_WARNING_THRESHOLD", "80.0")),
            budget_critical_threshold_percent=float(os.getenv("BUDGET_CRITICAL_THRESHOLD", "95.0")),
            budget_enforcement_action=os.getenv("BUDGET_ENFORCEMENT_ACTION", "throttle"),
            # Forecasting
            forecasting_enabled=os.getenv("COST_FORECASTING_ENABLED", "true").lower() == "true",
            forecasting_horizon_days=int(os.getenv("FORECASTING_HORIZON_DAYS", "30")),
            forecasting_confidence_interval=float(os.getenv("FORECASTING_CONFIDENCE", "0.95")),
            forecasting_min_data_points=int(os.getenv("FORECASTING_MIN_DATA_POINTS", "100")),
            forecasting_model_type=os.getenv("FORECASTING_MODEL_TYPE", "linear"),
            # Anomaly Detection
            anomaly_detection_enabled=os.getenv("ANOMALY_DETECTION_ENABLED", "true").lower() == "true",
            anomaly_threshold_std_dev=float(os.getenv("ANOMALY_THRESHOLD_STD_DEV", "2.5")),
            anomaly_window_hours=int(os.getenv("ANOMALY_WINDOW_HOURS", "24")),
            anomaly_min_requests=int(os.getenv("ANOMALY_MIN_REQUESTS", "10")),
            # Optimization
            optimization_target=os.getenv("OPTIMIZATION_TARGET", "cost"),
            cost_savings_threshold_percent=float(os.getenv("COST_SAVINGS_THRESHOLD", "10.0")),
            quality_degradation_tolerance=float(os.getenv("QUALITY_DEGRADATION_TOLERANCE", "0.05")),
            # Tenant/Project budgets (JSON format)
            per_tenant_budgets=_parse_json_dict(os.getenv("PER_TENANT_BUDGETS")),
            per_project_budgets=_parse_json_dict(os.getenv("PER_PROJECT_BUDGETS")),
            tenant_rate_limits=_parse_json_dict(os.getenv("TENANT_RATE_LIMITS"), int),
            # Alerts
            alerts_enabled=os.getenv("COST_ALERTS_ENABLED", "true").lower() == "true",
            alert_channels=_parse_list(os.getenv("COST_ALERT_CHANNELS", "webhook")),
            alert_webhook_url=os.getenv("COST_ALERT_WEBHOOK_URL"),
            # Cache
            cache_optimization_results=os.getenv("CACHE_OPTIMIZATION_RESULTS", "true").lower() == "true",
            cache_ttl_seconds=int(os.getenv("OPTIMIZATION_CACHE_TTL", "300")),
        )


def _parse_list(value: str | None) -> list[str]:
    """Parse comma-separated list from environment variable."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_json_dict(value: str | None, value_type=float) -> dict[str, any] | None:
    """Parse JSON dictionary from environment variable."""
    if not value:
        return None

    try:
        import json

        data = json.loads(value)
        if value_type != str:
            # Convert values to specified type
            return {k: value_type(v) for k, v in data.items()}
        return data
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
