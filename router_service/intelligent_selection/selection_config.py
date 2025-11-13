"""Configuration for intelligent model selection system."""

import os
from dataclasses import dataclass


@dataclass
class SelectionConfig:
    """Configuration for intelligent model selection."""

    # General Configuration
    enabled: bool = True
    cost_awareness_enabled: bool = True
    quality_optimization_enabled: bool = True
    local_model_preference: bool = True

    # Cost-Quality Tradeoff
    cost_weight: float = 0.4  # Weight for cost in selection (0-1)
    quality_weight: float = 0.4  # Weight for quality in selection (0-1)
    latency_weight: float = 0.2  # Weight for latency in selection (0-1)

    # Cost Optimization Thresholds
    max_cost_increase_percent: float = 20.0  # Max cost increase for quality
    min_quality_threshold: float = 0.7  # Minimum acceptable quality
    cost_savings_preference_percent: float = 15.0  # Prefer if saves >15%

    # Local Model Preferences
    local_model_cost_multiplier: float = 0.0  # Treat local models as free
    local_model_quality_bonus: float = 0.05  # 5% quality bonus for local models
    local_model_latency_penalty: float = 1.2  # 20% latency penalty for local models

    # Dynamic Pricing Integration
    use_real_time_pricing: bool = True
    pricing_staleness_tolerance_minutes: int = 60  # Max age for pricing data
    fallback_to_static_pricing: bool = True

    # Bandit Algorithm Enhancement
    exploration_rate: float = 0.05  # 5% exploration rate
    exploitation_decay: float = 0.95  # Decay factor for exploitation
    min_exploration_requests: int = 10  # Min requests before exploitation

    # Selection Strategy
    selection_strategy: str = "cost_aware_bandit"  # "cost_aware_bandit", "pure_cost", "pure_quality", "balanced"
    fallback_strategy: str = "cheapest_viable"  # Fallback when primary strategy fails

    # Tenant and Project Customization
    tenant_preferences: dict[str, dict[str, float]] = None  # tenant_id -> {cost_weight, quality_weight, latency_weight}
    project_preferences: dict[str, dict[str, float]] = None  # project_id -> preferences

    # Performance Tracking
    track_selection_performance: bool = True
    performance_window_hours: int = 24

    # Cache Configuration
    cache_selection_results: bool = True
    cache_ttl_seconds: int = 300  # 5 minutes

    @classmethod
    def from_environment(cls) -> "SelectionConfig":
        """Create configuration from environment variables."""
        return cls(
            # General
            enabled=os.getenv("INTELLIGENT_SELECTION_ENABLED", "true").lower() == "true",
            cost_awareness_enabled=os.getenv("COST_AWARENESS_ENABLED", "true").lower() == "true",
            quality_optimization_enabled=os.getenv("QUALITY_OPTIMIZATION_ENABLED", "true").lower() == "true",
            local_model_preference=os.getenv("LOCAL_MODEL_PREFERENCE", "true").lower() == "true",
            # Weights
            cost_weight=float(os.getenv("SELECTION_COST_WEIGHT", "0.4")),
            quality_weight=float(os.getenv("SELECTION_QUALITY_WEIGHT", "0.4")),
            latency_weight=float(os.getenv("SELECTION_LATENCY_WEIGHT", "0.2")),
            # Thresholds
            max_cost_increase_percent=float(os.getenv("MAX_COST_INCREASE_PERCENT", "20.0")),
            min_quality_threshold=float(os.getenv("MIN_QUALITY_THRESHOLD", "0.7")),
            cost_savings_preference_percent=float(os.getenv("COST_SAVINGS_PREFERENCE", "15.0")),
            # Local Model Preferences
            local_model_cost_multiplier=float(os.getenv("LOCAL_MODEL_COST_MULTIPLIER", "0.0")),
            local_model_quality_bonus=float(os.getenv("LOCAL_MODEL_QUALITY_BONUS", "0.05")),
            local_model_latency_penalty=float(os.getenv("LOCAL_MODEL_LATENCY_PENALTY", "1.2")),
            # Pricing Integration
            use_real_time_pricing=os.getenv("USE_REAL_TIME_PRICING", "true").lower() == "true",
            pricing_staleness_tolerance_minutes=int(os.getenv("PRICING_STALENESS_TOLERANCE", "60")),
            fallback_to_static_pricing=os.getenv("FALLBACK_TO_STATIC_PRICING", "true").lower() == "true",
            # Bandit Algorithm
            exploration_rate=float(os.getenv("EXPLORATION_RATE", "0.05")),
            exploitation_decay=float(os.getenv("EXPLOITATION_DECAY", "0.95")),
            min_exploration_requests=int(os.getenv("MIN_EXPLORATION_REQUESTS", "10")),
            # Strategy
            selection_strategy=os.getenv("SELECTION_STRATEGY", "cost_aware_bandit"),
            fallback_strategy=os.getenv("FALLBACK_STRATEGY", "cheapest_viable"),
            # Customization
            tenant_preferences=_parse_json_preferences(os.getenv("TENANT_PREFERENCES")),
            project_preferences=_parse_json_preferences(os.getenv("PROJECT_PREFERENCES")),
            # Performance
            track_selection_performance=os.getenv("TRACK_SELECTION_PERFORMANCE", "true").lower() == "true",
            performance_window_hours=int(os.getenv("PERFORMANCE_WINDOW_HOURS", "24")),
            # Cache
            cache_selection_results=os.getenv("CACHE_SELECTION_RESULTS", "true").lower() == "true",
            cache_ttl_seconds=int(os.getenv("SELECTION_CACHE_TTL", "300")),
        )


def _parse_json_preferences(value: str | None) -> dict[str, dict[str, float]] | None:
    """Parse JSON preferences from environment variable."""
    if not value:
        return None

    try:
        import json

        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


# Model categories for local preference
LOCAL_MODEL_INDICATORS = [
    "llama",
    "mistral",
    "vicuna",
    "alpaca",
    "falcon",
    "mpt",
    "dolly",
    "stablelm",
    "redpajama",
    "openchat",
    "wizard",
    "orca",
    "phi",
]

CLOUD_PROVIDERS = ["openai", "anthropic", "google", "cohere", "ai21"]
LOCAL_PROVIDERS = ["ollama", "vllm", "text-generation-webui", "llama.cpp", "local"]
