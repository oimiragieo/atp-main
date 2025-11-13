"""Main pricing manager that coordinates all pricing components."""

import asyncio
import logging
from typing import Any

from .pricing_alerts import PricingAlertManager
from .pricing_cache import PricingCache
from .pricing_config import PricingConfig
from .pricing_monitor import PricingMonitor

logger = logging.getLogger(__name__)


class PricingManager:
    """Main manager for the real-time pricing monitoring system."""

    def __init__(self, config: PricingConfig | None = None):
        self.config = config or PricingConfig.from_environment()

        # Initialize components
        self.monitor = PricingMonitor(self.config)
        self.cache = PricingCache(ttl_seconds=self.config.cache_ttl_seconds, cache_prefix="pricing:")
        self.alert_manager = PricingAlertManager(self.config) if self.config.alerts_enabled else None

        # Integration with existing cost tracking
        self._cost_integration_enabled = True

        logger.info("Pricing manager initialized")

    async def start(self) -> None:
        """Start the pricing monitoring system."""
        if self.config.enabled:
            await self.monitor.start_monitoring()
            logger.info("Pricing monitoring system started")
        else:
            logger.info("Pricing monitoring system is disabled")

    async def stop(self) -> None:
        """Stop the pricing monitoring system."""
        await self.monitor.stop_monitoring()
        logger.info("Pricing monitoring system stopped")

    async def get_model_pricing(
        self, provider: str, model: str, force_refresh: bool = False
    ) -> dict[str, float] | None:
        """Get current pricing for a model."""
        return await self.monitor.get_current_pricing(provider, model, force_refresh)

    async def get_all_pricing(self, force_refresh: bool = False) -> dict[str, dict[str, dict[str, float]]]:
        """Get current pricing for all models."""
        return await self.monitor.get_all_current_pricing(force_refresh)

    async def calculate_request_cost(
        self, provider: str, model: str, input_tokens: int, output_tokens: int, use_cached_pricing: bool = True
    ) -> dict[str, Any]:
        """Calculate cost for a request using current pricing."""
        try:
            # Get current pricing
            pricing = await self.get_model_pricing(provider, model, not use_cached_pricing)

            if not pricing:
                logger.warning(f"No pricing data available for {provider}:{model}")
                return {"error": "No pricing data available", "provider": provider, "model": model}

            # Calculate costs
            input_cost_per_1k = pricing.get("input", 0.0)
            output_cost_per_1k = pricing.get("output", 0.0)

            input_cost = (input_tokens / 1000.0) * input_cost_per_1k
            output_cost = (output_tokens / 1000.0) * output_cost_per_1k
            total_cost = input_cost + output_cost

            return {
                "provider": provider,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "pricing": pricing,
                "input_cost_usd": input_cost,
                "output_cost_usd": output_cost,
                "total_cost_usd": total_cost,
                "calculated_at": asyncio.get_event_loop().time(),
            }

        except Exception as e:
            logger.error(f"Error calculating request cost: {e}")
            return {"error": str(e), "provider": provider, "model": model}

    async def validate_actual_cost(
        self, provider: str, model: str, input_tokens: int, output_tokens: int, actual_cost: float
    ) -> dict[str, Any]:
        """Validate actual cost against expected pricing."""
        # Calculate expected cost
        expected_result = await self.calculate_request_cost(provider, model, input_tokens, output_tokens)

        if "error" in expected_result:
            return expected_result

        expected_result["total_cost_usd"]

        # Validate with monitor
        validation_result = await self.monitor.validate_pricing_accuracy(
            provider=provider,
            model=model,
            actual_cost=actual_cost,
            tokens_used=input_tokens + output_tokens,
            token_type="combined",  # For total cost validation
        )

        # Enhance with our calculation
        validation_result.update(
            {
                "expected_breakdown": expected_result,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            }
        )

        return validation_result

    async def get_pricing_trends(
        self, provider: str | None = None, model: str | None = None, hours: int = 24
    ) -> dict[str, Any]:
        """Get pricing trends and changes."""
        changes_report = await self.monitor.get_pricing_changes_report(hours)

        # Filter by provider/model if specified
        if provider or model:
            filtered_changes = []
            for change in changes_report.get("changes", []):
                if provider and change.get("provider") != provider:
                    continue
                if model and change.get("model") != model:
                    continue
                filtered_changes.append(change)

            changes_report["changes"] = filtered_changes
            changes_report["total_changes"] = len(filtered_changes)

        return changes_report

    async def get_cost_optimization_recommendations(
        self,
        current_usage: dict[str, dict[str, int]],  # provider -> model -> token_count
    ) -> list[dict[str, Any]]:
        """Get cost optimization recommendations based on current usage."""
        recommendations = []

        try:
            # Get all current pricing
            all_pricing = await self.get_all_pricing()

            for provider, models in current_usage.items():
                if provider not in all_pricing:
                    continue

                for model, token_count in models.items():
                    if model not in all_pricing[provider]:
                        continue

                    current_pricing = all_pricing[provider][model]
                    current_cost = (token_count / 1000.0) * current_pricing.get("input", 0.0)

                    # Find cheaper alternatives
                    alternatives = []
                    for alt_provider, alt_models in all_pricing.items():
                        for alt_model, alt_pricing in alt_models.items():
                            if alt_provider == provider and alt_model == model:
                                continue

                            alt_cost = (token_count / 1000.0) * alt_pricing.get("input", 0.0)
                            if alt_cost < current_cost:
                                savings = current_cost - alt_cost
                                savings_percent = (savings / current_cost) * 100

                                alternatives.append(
                                    {
                                        "provider": alt_provider,
                                        "model": alt_model,
                                        "cost_usd": alt_cost,
                                        "savings_usd": savings,
                                        "savings_percent": savings_percent,
                                    }
                                )

                    # Sort by savings
                    alternatives.sort(key=lambda x: x["savings_usd"], reverse=True)

                    if alternatives:
                        recommendations.append(
                            {
                                "current": {
                                    "provider": provider,
                                    "model": model,
                                    "cost_usd": current_cost,
                                    "token_count": token_count,
                                },
                                "alternatives": alternatives[:3],  # Top 3 alternatives
                                "max_savings_usd": alternatives[0]["savings_usd"],
                                "max_savings_percent": alternatives[0]["savings_percent"],
                            }
                        )

        except Exception as e:
            logger.error(f"Error generating cost optimization recommendations: {e}")

        return recommendations

    async def get_system_health(self) -> dict[str, Any]:
        """Get overall system health status."""
        health = {"pricing_monitoring": True, "components": {}, "alerts": {}, "cache": {}}

        try:
            # Monitor health
            monitor_stats = self.monitor.get_monitoring_statistics()
            health["components"]["monitor"] = {
                "status": "healthy" if monitor_stats["is_monitoring"] else "stopped",
                "providers_configured": monitor_stats["providers_configured"],
                "update_count": monitor_stats["update_count"],
                "error_count": monitor_stats["error_count"],
            }

            # Alert manager health
            if self.alert_manager:
                alert_stats = self.alert_manager.get_alert_statistics()
                health["alerts"] = {
                    "enabled": alert_stats["alerts_enabled"],
                    "total_sent": alert_stats["total_alerts_sent"],
                    "channels": alert_stats["alert_channels"],
                }

            # Cache health
            cache_stats = await self.cache.get_cache_statistics()
            health["cache"] = {
                "total_models": cache_stats.get("total_cached_models", 0),
                "stale_entries": cache_stats.get("stale_entries", 0),
                "provider_counts": cache_stats.get("provider_counts", {}),
            }

            # Staleness check
            stale_report = await self.monitor.get_stale_pricing_report()
            health["staleness"] = {
                "stale_count": stale_report["stale_count"],
                "threshold_seconds": stale_report["staleness_threshold_seconds"],
            }

            # Overall health determination
            health["pricing_monitoring"] = (
                health["components"]["monitor"]["status"] == "healthy"
                and health["staleness"]["stale_count"] < 10  # Arbitrary threshold
            )

        except Exception as e:
            logger.error(f"Error getting system health: {e}")
            health["error"] = str(e)
            health["pricing_monitoring"] = False

        return health

    async def refresh_all_pricing(self) -> dict[str, Any]:
        """Force refresh of all pricing data."""
        try:
            logger.info("Starting full pricing refresh...")

            # Clear cache
            cleared_count = await self.cache.clear_pricing_cache()

            # Force refresh all pricing
            all_pricing = await self.get_all_pricing(force_refresh=True)

            # Count updated models
            updated_count = sum(len(models) for models in all_pricing.values())

            result = {
                "success": True,
                "cleared_cache_entries": cleared_count,
                "updated_models": updated_count,
                "providers": list(all_pricing.keys()),
                "refreshed_at": asyncio.get_event_loop().time(),
            }

            logger.info(f"Pricing refresh completed: {updated_count} models updated")
            return result

        except Exception as e:
            logger.error(f"Error during pricing refresh: {e}")
            return {"success": False, "error": str(e)}


# Global pricing manager instance
_pricing_manager: PricingManager | None = None


def get_pricing_manager() -> PricingManager:
    """Get the global pricing manager instance."""
    global _pricing_manager
    if _pricing_manager is None:
        _pricing_manager = PricingManager()
    return _pricing_manager


async def initialize_pricing_manager(config: PricingConfig | None = None) -> PricingManager:
    """Initialize and start the pricing manager."""
    global _pricing_manager
    _pricing_manager = PricingManager(config)

    # Start monitoring
    await _pricing_manager.start()

    logger.info("Pricing manager initialized and started")
    return _pricing_manager
