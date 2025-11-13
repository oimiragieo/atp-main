"""Configuration for the real-time pricing monitoring system."""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class PricingConfig:
    """Configuration for real-time pricing monitoring."""
    
    # General Configuration
    enabled: bool = True
    update_interval_seconds: int = 300  # 5 minutes
    staleness_threshold_seconds: int = 3600  # 1 hour
    
    # Provider API Configuration
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    
    # API Rate Limiting
    api_rate_limit_per_minute: int = 60
    api_timeout_seconds: float = 30.0
    api_retry_attempts: int = 3
    api_retry_delay_seconds: float = 1.0
    
    # Pricing Change Detection
    change_detection_enabled: bool = True
    change_threshold_percent: float = 5.0  # Alert on 5% price changes
    significant_change_percent: float = 20.0  # Major alert on 20% changes
    
    # Cost Validation
    validation_enabled: bool = True
    validation_tolerance_percent: float = 10.0  # Allow 10% variance
    validation_sample_size: int = 100  # Sample size for validation
    
    # Alerting Configuration
    alerts_enabled: bool = True
    alert_channels: List[str] = None  # ["email", "slack", "webhook"]
    alert_webhook_url: Optional[str] = None
    alert_email_recipients: List[str] = None
    
    # Caching Configuration
    cache_ttl_seconds: int = 1800  # 30 minutes
    cache_enabled: bool = True
    
    # Metrics Configuration
    metrics_enabled: bool = True
    detailed_metrics: bool = False
    
    @classmethod
    def from_environment(cls) -> 'PricingConfig':
        """Create pricing configuration from environment variables."""
        return cls(
            # General Configuration
            enabled=os.getenv("PRICING_MONITORING_ENABLED", "true").lower() == "true",
            update_interval_seconds=int(os.getenv("PRICING_UPDATE_INTERVAL", "300")),
            staleness_threshold_seconds=int(os.getenv("PRICING_STALENESS_THRESHOLD", "3600")),
            
            # Provider API Configuration
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            
            # API Rate Limiting
            api_rate_limit_per_minute=int(os.getenv("PRICING_API_RATE_LIMIT", "60")),
            api_timeout_seconds=float(os.getenv("PRICING_API_TIMEOUT", "30.0")),
            api_retry_attempts=int(os.getenv("PRICING_API_RETRY_ATTEMPTS", "3")),
            api_retry_delay_seconds=float(os.getenv("PRICING_API_RETRY_DELAY", "1.0")),
            
            # Change Detection
            change_detection_enabled=os.getenv("PRICING_CHANGE_DETECTION", "true").lower() == "true",
            change_threshold_percent=float(os.getenv("PRICING_CHANGE_THRESHOLD", "5.0")),
            significant_change_percent=float(os.getenv("PRICING_SIGNIFICANT_CHANGE", "20.0")),
            
            # Cost Validation
            validation_enabled=os.getenv("PRICING_VALIDATION_ENABLED", "true").lower() == "true",
            validation_tolerance_percent=float(os.getenv("PRICING_VALIDATION_TOLERANCE", "10.0")),
            validation_sample_size=int(os.getenv("PRICING_VALIDATION_SAMPLE_SIZE", "100")),
            
            # Alerting
            alerts_enabled=os.getenv("PRICING_ALERTS_ENABLED", "true").lower() == "true",
            alert_channels=_parse_list(os.getenv("PRICING_ALERT_CHANNELS", "webhook")),
            alert_webhook_url=os.getenv("PRICING_ALERT_WEBHOOK_URL"),
            alert_email_recipients=_parse_list(os.getenv("PRICING_ALERT_EMAIL_RECIPIENTS")),
            
            # Caching
            cache_ttl_seconds=int(os.getenv("PRICING_CACHE_TTL", "1800")),
            cache_enabled=os.getenv("PRICING_CACHE_ENABLED", "true").lower() == "true",
            
            # Metrics
            metrics_enabled=os.getenv("PRICING_METRICS_ENABLED", "true").lower() == "true",
            detailed_metrics=os.getenv("PRICING_DETAILED_METRICS", "false").lower() == "true"
        )


def _parse_list(value: Optional[str]) -> List[str]:
    """Parse comma-separated list from environment variable."""
    if not value:
        return []
    return [item.strip() for item in value.split(',') if item.strip()]


# Provider-specific model mappings
PROVIDER_MODEL_MAPPINGS = {
    "openai": {
        "gpt-4": "gpt-4",
        "gpt-4-turbo": "gpt-4-turbo-preview",
        "gpt-4-vision": "gpt-4-vision-preview",
        "gpt-3.5-turbo": "gpt-3.5-turbo",
        "gpt-3.5-turbo-16k": "gpt-3.5-turbo-16k",
        "text-embedding-ada-002": "text-embedding-ada-002",
        "text-embedding-3-small": "text-embedding-3-small",
        "text-embedding-3-large": "text-embedding-3-large"
    },
    "anthropic": {
        "claude-3-opus": "claude-3-opus-20240229",
        "claude-3-sonnet": "claude-3-sonnet-20240229", 
        "claude-3-haiku": "claude-3-haiku-20240307",
        "claude-2.1": "claude-2.1",
        "claude-2": "claude-2.0",
        "claude-instant": "claude-instant-1.2"
    },
    "google": {
        "gemini-pro": "gemini-pro",
        "gemini-pro-vision": "gemini-pro-vision",
        "gemini-ultra": "gemini-ultra",
        "text-bison": "text-bison-001",
        "chat-bison": "chat-bison-001",
        "code-bison": "code-bison-001"
    }
}

# Default pricing fallbacks (USD per 1K tokens)
DEFAULT_PRICING = {
    "openai": {
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002},
        "text-embedding-ada-002": {"input": 0.0001, "output": 0.0}
    },
    "anthropic": {
        "claude-3-opus": {"input": 0.015, "output": 0.075},
        "claude-3-sonnet": {"input": 0.003, "output": 0.015},
        "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
        "claude-2.1": {"input": 0.008, "output": 0.024}
    },
    "google": {
        "gemini-pro": {"input": 0.0005, "output": 0.0015},
        "gemini-pro-vision": {"input": 0.0025, "output": 0.01},
        "text-bison": {"input": 0.001, "output": 0.001}
    }
}