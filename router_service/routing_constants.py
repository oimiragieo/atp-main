"""Shared constants for routing functionality.

This module provides model catalog management, loading models either from
registered adapters (dynamic) or from a static fallback catalog.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Candidate:
    """Represents a model candidate for routing decisions.

    Attributes:
        name: Model identifier (e.g., "claude-3-5-sonnet-20241022")
        cost_per_1k_tokens: Cost in USD per 1000 tokens
        quality_pred: Predicted quality score (0.0-1.0)
        latency_p95: 95th percentile latency in milliseconds
        region: Geographic region (e.g., "us-west")
        adapter_type: Type of adapter providing this model (e.g., "anthropic")
        adapter_endpoint: gRPC endpoint for the adapter
    """

    name: str
    cost_per_1k_tokens: float
    quality_pred: float  # 0-1
    latency_p95: int  # ms
    region: str = "us-west"  # Default region
    adapter_type: str = ""  # NEW: Which adapter provides this model
    adapter_endpoint: str = ""  # NEW: Adapter gRPC endpoint


def load_catalog_from_adapters() -> list[Candidate]:
    """Load model catalog dynamically from registered adapters.

    This function queries the adapter registry to discover available models
    from all registered and healthy adapters. Falls back to static catalog
    if no adapters are available.

    Returns:
        List of Candidate objects representing available models

    Note:
        This function is safe to call even if no adapters are registered.
        It will return the static catalog as a fallback.
    """
    try:
        from router_service.adapter_registry import get_adapter_registry

        registry = get_adapter_registry()
        catalog = []

        # Get all registered adapters
        adapters = registry.get_all_adapters()

        for adapter in adapters:
            # Skip unhealthy adapters
            if not adapter.is_healthy():
                logger.warning(f"Skipping unhealthy adapter: {adapter.adapter_id}")
                continue

            # Create candidate for each model provided by this adapter
            for model_id in adapter.models:
                # Convert cost from micros to USD per 1K tokens
                cost_per_1k = (
                    (adapter.cost_per_token_micros or 1000) / 1_000_000.0 if adapter.cost_per_token_micros else 1.0
                )

                # Use adapter latency metrics if available
                latency = int(adapter.p95_latency_ms or 1000)

                # Extract endpoint from health_endpoint if available
                endpoint = adapter.health_endpoint or ""

                candidate = Candidate(
                    name=model_id,
                    cost_per_1k_tokens=cost_per_1k,
                    quality_pred=0.80,  # Default, will be learned over time
                    latency_p95=latency,
                    region=adapter.metadata.get("region", "us-west") if adapter.metadata else "us-west",
                    adapter_type=adapter.adapter_type,
                    adapter_endpoint=endpoint,
                )
                catalog.append(candidate)
                logger.debug(f"Added model {model_id} from adapter {adapter.adapter_id}")

        if catalog:
            logger.info(f"Loaded {len(catalog)} models from {len(adapters)} adapters")
            return catalog
        else:
            logger.warning("No models found in adapter registry, using static catalog")
            return STATIC_CATALOG

    except Exception as e:
        logger.error(f"Failed to load catalog from adapters: {e}", exc_info=True)
        logger.warning("Falling back to static catalog")
        return STATIC_CATALOG


# Static fallback catalog for testing and development
# Used when no adapters are registered or if adapter loading fails
STATIC_CATALOG = [
    Candidate("cheap-model", 0.4, 0.70, 900, "us-west", "", ""),
    # Experimental model starts as shadow (status in registry governs use in plan)
    Candidate("exp-model", 0.8, 0.78, 950, "us-east", "", ""),
    Candidate("mid-model", 1.0, 0.80, 1100, "eu-west", "", ""),
    Candidate("premium-model", 2.0, 0.90, 1400, "asia-east", "", ""),
]

# Dynamic catalog: loaded from adapters at module initialization
# This will be refreshed periodically in production
CATALOG = load_catalog_from_adapters()

# Quality thresholds for routing decisions
QUALITY_THRESH = {"fast": 0.60, "balanced": 0.75, "high": 0.85}


def refresh_catalog() -> None:
    """Refresh the model catalog from adapters.

    This function should be called periodically to update the catalog
    with newly registered adapters or changed adapter capabilities.
    """
    global CATALOG
    CATALOG = load_catalog_from_adapters()
    logger.info("Model catalog refreshed")
