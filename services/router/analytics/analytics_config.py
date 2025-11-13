"""Configuration for the advanced analytics system."""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class AnalyticsConfig:
    """Configuration for advanced analytics and insights."""
    
    # General Configuration
    enabled: bool = True
    data_retention_days: int = 90
    analysis_interval_minutes: int = 15
    
    # Request Analytics
    request_analytics_enabled: bool = True
    request_pattern_analysis: bool = True
    request_clustering_enabled: bool = True
    request_anomaly_detection: bool = True
    
    # Performance Analytics
    performance_analytics_enabled: bool = True
    latency_analysis: bool = True
    throughput_analysis: bool = True
    error_rate_analysis: bool = True
    quality_analysis: bool = True
    
    # Business Intelligence
    business_intelligence_enabled: bool = True
    cost_analysis: bool = True
    usage_forecasting: bool = True
    capacity_planning: bool = True
    roi_analysis: bool = True
    
    # Anomaly Detection
    anomaly_detection_enabled: bool = True
    anomaly_sensitivity: float = 0.95  # 95th percentile
    anomaly_window_hours: int = 24
    anomaly_min_samples: int = 100
    
    # Trend Analysis
    trend_analysis_enabled: bool = True
    trend_window_days: int = 7
    seasonal_analysis: bool = True
    forecast_horizon_days: int = 30
    
    # Insights Generation
    insights_enabled: bool = True
    insights_update_interval_hours: int = 6
    insights_confidence_threshold: float = 0.8
    
    # Data Sources
    use_request_logs: bool = True
    use_performance_metrics: bool = True
    use_cost_data: bool = True
    use_user_feedback: bool = True
    
    # Storage Configuration
    analytics_database_url: Optional[str] = None
    time_series_database_url: Optional[str] = None
    cache_analytics_results: bool = True
    analytics_cache_ttl_minutes: int = 60
    
    # Export Configuration
    export_enabled: bool = True
    export_formats: List[str] = None  # ["json", "csv", "parquet"]
    export_schedule_cron: str = "0 2 * * *"  # Daily at 2 AM
    
    # Alert Configuration
    alerts_enabled: bool = True
    alert_thresholds: Dict[str, float] = None
    alert_channels: List[str] = None
    
    # Machine Learning
    ml_enabled: bool = True
    ml_model_update_interval_hours: int = 24
    ml_feature_engineering: bool = True
    ml_auto_retraining: bool = True
    
    @classmethod
    def from_environment(cls) -> 'AnalyticsConfig':
        """Create analytics configuration from environment variables."""
        return cls(
            # General Configuration
            enabled=os.getenv("ANALYTICS_ENABLED", "true").lower() == "true",
            data_retention_days=int(os.getenv("ANALYTICS_DATA_RETENTION_DAYS", "90")),
            analysis_interval_minutes=int(os.getenv("ANALYTICS_INTERVAL_MINUTES", "15")),
            
            # Request Analytics
            request_analytics_enabled=os.getenv("ANALYTICS_REQUEST_ENABLED", "true").lower() == "true",
            request_pattern_analysis=os.getenv("ANALYTICS_REQUEST_PATTERNS", "true").lower() == "true",
            request_clustering_enabled=os.getenv("ANALYTICS_REQUEST_CLUSTERING", "true").lower() == "true",
            request_anomaly_detection=os.getenv("ANALYTICS_REQUEST_ANOMALIES", "true").lower() == "true",
            
            # Performance Analytics
            performance_analytics_enabled=os.getenv("ANALYTICS_PERFORMANCE_ENABLED", "true").lower() == "true",
            latency_analysis=os.getenv("ANALYTICS_LATENCY_ANALYSIS", "true").lower() == "true",
            throughput_analysis=os.getenv("ANALYTICS_THROUGHPUT_ANALYSIS", "true").lower() == "true",
            error_rate_analysis=os.getenv("ANALYTICS_ERROR_RATE_ANALYSIS", "true").lower() == "true",
            quality_analysis=os.getenv("ANALYTICS_QUALITY_ANALYSIS", "true").lower() == "true",
            
            # Business Intelligence
            business_intelligence_enabled=os.getenv("ANALYTICS_BI_ENABLED", "true").lower() == "true",
            cost_analysis=os.getenv("ANALYTICS_COST_ANALYSIS", "true").lower() == "true",
            usage_forecasting=os.getenv("ANALYTICS_USAGE_FORECASTING", "true").lower() == "true",
            capacity_planning=os.getenv("ANALYTICS_CAPACITY_PLANNING", "true").lower() == "true",
            roi_analysis=os.getenv("ANALYTICS_ROI_ANALYSIS", "true").lower() == "true",
            
            # Anomaly Detection
            anomaly_detection_enabled=os.getenv("ANALYTICS_ANOMALY_DETECTION", "true").lower() == "true",
            anomaly_sensitivity=float(os.getenv("ANALYTICS_ANOMALY_SENSITIVITY", "0.95")),
            anomaly_window_hours=int(os.getenv("ANALYTICS_ANOMALY_WINDOW_HOURS", "24")),
            anomaly_min_samples=int(os.getenv("ANALYTICS_ANOMALY_MIN_SAMPLES", "100")),
            
            # Trend Analysis
            trend_analysis_enabled=os.getenv("ANALYTICS_TREND_ANALYSIS", "true").lower() == "true",
            trend_window_days=int(os.getenv("ANALYTICS_TREND_WINDOW_DAYS", "7")),
            seasonal_analysis=os.getenv("ANALYTICS_SEASONAL_ANALYSIS", "true").lower() == "true",
            forecast_horizon_days=int(os.getenv("ANALYTICS_FORECAST_HORIZON_DAYS", "30")),
            
            # Insights Generation
            insights_enabled=os.getenv("ANALYTICS_INSIGHTS_ENABLED", "true").lower() == "true",
            insights_update_interval_hours=int(os.getenv("ANALYTICS_INSIGHTS_INTERVAL_HOURS", "6")),
            insights_confidence_threshold=float(os.getenv("ANALYTICS_INSIGHTS_CONFIDENCE", "0.8")),
            
            # Data Sources
            use_request_logs=os.getenv("ANALYTICS_USE_REQUEST_LOGS", "true").lower() == "true",
            use_performance_metrics=os.getenv("ANALYTICS_USE_PERFORMANCE_METRICS", "true").lower() == "true",
            use_cost_data=os.getenv("ANALYTICS_USE_COST_DATA", "true").lower() == "true",
            use_user_feedback=os.getenv("ANALYTICS_USE_USER_FEEDBACK", "true").lower() == "true",
            
            # Storage Configuration
            analytics_database_url=os.getenv("ANALYTICS_DATABASE_URL"),
            time_series_database_url=os.getenv("ANALYTICS_TIMESERIES_DATABASE_URL"),
            cache_analytics_results=os.getenv("ANALYTICS_CACHE_RESULTS", "true").lower() == "true",
            analytics_cache_ttl_minutes=int(os.getenv("ANALYTICS_CACHE_TTL_MINUTES", "60")),
            
            # Export Configuration
            export_enabled=os.getenv("ANALYTICS_EXPORT_ENABLED", "true").lower() == "true",
            export_formats=_parse_list(os.getenv("ANALYTICS_EXPORT_FORMATS", "json,csv")),
            export_schedule_cron=os.getenv("ANALYTICS_EXPORT_SCHEDULE", "0 2 * * *"),
            
            # Alert Configuration
            alerts_enabled=os.getenv("ANALYTICS_ALERTS_ENABLED", "true").lower() == "true",
            alert_thresholds=_parse_dict(os.getenv("ANALYTICS_ALERT_THRESHOLDS")),
            alert_channels=_parse_list(os.getenv("ANALYTICS_ALERT_CHANNELS", "webhook")),
            
            # Machine Learning
            ml_enabled=os.getenv("ANALYTICS_ML_ENABLED", "true").lower() == "true",
            ml_model_update_interval_hours=int(os.getenv("ANALYTICS_ML_UPDATE_INTERVAL_HOURS", "24")),
            ml_feature_engineering=os.getenv("ANALYTICS_ML_FEATURE_ENGINEERING", "true").lower() == "true",
            ml_auto_retraining=os.getenv("ANALYTICS_ML_AUTO_RETRAINING", "true").lower() == "true"
        )


def _parse_list(value: Optional[str]) -> List[str]:
    """Parse comma-separated list from environment variable."""
    if not value:
        return []
    return [item.strip() for item in value.split(',') if item.strip()]


def _parse_dict(value: Optional[str]) -> Dict[str, float]:
    """Parse key=value pairs from environment variable."""
    if not value:
        return {}
    
    result = {}
    for pair in value.split(','):
        if '=' in pair:
            key, val = pair.split('=', 1)
            try:
                result[key.strip()] = float(val.strip())
            except ValueError:
                pass
    return result


# Default alert thresholds
DEFAULT_ALERT_THRESHOLDS = {
    "error_rate_percent": 5.0,
    "latency_p95_ms": 5000.0,
    "cost_increase_percent": 20.0,
    "throughput_decrease_percent": 30.0,
    "anomaly_score": 0.95
}

# Default export formats
DEFAULT_EXPORT_FORMATS = ["json", "csv"]

# Default alert channels
DEFAULT_ALERT_CHANNELS = ["webhook"]