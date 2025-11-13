"""Real-time pricing monitoring with change detection and alerting."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Set

from .pricing_config import PricingConfig, PROVIDER_MODEL_MAPPINGS
from .provider_apis import create_pricing_api, BasePricingAPI, PricingAPIError
from .pricing_cache import PricingCache
from .pricing_alerts import PricingAlertManager

logger = logging.getLogger(__name__)


class PricingMonitor:
    """Real-time pricing monitor with change detection and alerting."""
    
    def __init__(self, config: Optional[PricingConfig] = None):
        self.config = config or PricingConfig.from_environment()
        
        # Initialize components
        self.cache = PricingCache(
            ttl_seconds=self.config.cache_ttl_seconds,
            cache_prefix="pricing:"
        )
        
        self.alert_manager = PricingAlertManager(self.config) if self.config.alerts_enabled else None
        
        # Initialize provider APIs
        self.provider_apis: Dict[str, BasePricingAPI] = {}
        self._initialize_provider_apis()
        
        # Monitoring state
        self._monitoring_task: Optional[asyncio.Task] = None
        self._is_monitoring = False
        self._last_update_times: Dict[str, float] = {}
        
        # Metrics tracking
        self._update_count = 0
        self._error_count = 0
        self._change_count = 0
        
        logger.info(f"Pricing monitor initialized with {len(self.provider_apis)} providers")
    
    def _initialize_provider_apis(self) -> None:
        """Initialize provider API clients."""
        if self.config.openai_api_key:
            try:
                self.provider_apis["openai"] = create_pricing_api(
                    "openai",
                    api_key=self.config.openai_api_key,
                    timeout=self.config.api_timeout_seconds,
                    retry_attempts=self.config.api_retry_attempts,
                    retry_delay=self.config.api_retry_delay_seconds
                )
                logger.info("OpenAI pricing API initialized")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI pricing API: {e}")
        
        if self.config.anthropic_api_key:
            try:
                self.provider_apis["anthropic"] = create_pricing_api(
                    "anthropic",
                    api_key=self.config.anthropic_api_key,
                    timeout=self.config.api_timeout_seconds,
                    retry_attempts=self.config.api_retry_attempts,
                    retry_delay=self.config.api_retry_delay_seconds
                )
                logger.info("Anthropic pricing API initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Anthropic pricing API: {e}")
        
        if self.config.google_api_key:
            try:
                self.provider_apis["google"] = create_pricing_api(
                    "google",
                    api_key=self.config.google_api_key,
                    timeout=self.config.api_timeout_seconds,
                    retry_attempts=self.config.api_retry_attempts,
                    retry_delay=self.config.api_retry_delay_seconds
                )
                logger.info("Google pricing API initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Google pricing API: {e}")
        
        # Always add mock API for testing
        try:
            mock_api = create_pricing_api("mock", provider_name="mock")
            # Set some test data
            mock_api.set_pricing_data({
                "test-model": {"input": 0.01, "output": 0.03},
                "test-model-2": {"input": 0.005, "output": 0.015}
            })
            self.provider_apis["mock"] = mock_api
        except Exception as e:
            logger.error(f"Failed to initialize mock pricing API: {e}")
    
    async def start_monitoring(self) -> None:
        """Start the pricing monitoring loop."""
        if self._is_monitoring:
            logger.warning("Pricing monitoring is already running")
            return
        
        if not self.config.enabled:
            logger.info("Pricing monitoring is disabled")
            return
        
        self._is_monitoring = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Pricing monitoring started")
    
    async def stop_monitoring(self) -> None:
        """Stop the pricing monitoring loop."""
        self._is_monitoring = False
        
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Pricing monitoring stopped")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        while self._is_monitoring:
            try:
                await self._update_all_pricing()
                await asyncio.sleep(self.config.update_interval_seconds)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in pricing monitoring loop: {e}")
                self._error_count += 1
                await asyncio.sleep(min(self.config.update_interval_seconds, 60))
    
    async def _update_all_pricing(self) -> None:
        """Update pricing for all providers and models."""
        update_tasks = []
        
        for provider_name, api in self.provider_apis.items():
            if provider_name in PROVIDER_MODEL_MAPPINGS:
                models = list(PROVIDER_MODEL_MAPPINGS[provider_name].keys())
                for model in models:
                    task = asyncio.create_task(
                        self._update_model_pricing(provider_name, model, api)
                    )
                    update_tasks.append(task)
        
        # Execute all updates concurrently
        if update_tasks:
            results = await asyncio.gather(*update_tasks, return_exceptions=True)
            
            # Count successes and failures
            success_count = sum(1 for r in results if r is True)
            error_count = sum(1 for r in results if isinstance(r, Exception))
            
            logger.debug(f"Pricing update completed: {success_count} success, {error_count} errors")
            self._update_count += success_count
            self._error_count += error_count
    
    async def _update_model_pricing(
        self,
        provider: str,
        model: str,
        api: BasePricingAPI
    ) -> bool:
        """Update pricing for a specific model."""
        try:
            # Get current pricing from API
            pricing = await api.get_model_pricing(model)
            
            if not pricing:
                logger.warning(f"No pricing data returned for {provider}:{model}")
                return False
            
            # Store in cache (this will detect changes automatically)
            success = await self.cache.set_pricing(
                provider=provider,
                model=model,
                pricing=pricing,
                metadata={
                    "updated_at": time.time(),
                    "api_provider": api.get_provider_name()
                }
            )
            
            if success:
                self._last_update_times[f"{provider}:{model}"] = time.time()
                
                # Check for significant changes and send alerts
                if self.config.change_detection_enabled:
                    await self._check_for_alerts(provider, model, pricing)
            
            return success
        
        except PricingAPIError as e:
            logger.error(f"API error updating pricing for {provider}:{model}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating pricing for {provider}:{model}: {e}")
            return False
    
    async def _check_for_alerts(
        self,
        provider: str,
        model: str,
        current_pricing: Dict[str, float]
    ) -> None:
        """Check for pricing changes that require alerts."""
        if not self.alert_manager:
            return
        
        try:
            # Get recent changes from cache
            changes = await self.cache.get_pricing_changes(
                provider=provider,
                model=model,
                since_timestamp=time.time() - 300  # Last 5 minutes
            )
            
            for change in changes:
                change_percent = abs(change.get("change_percent", 0))
                
                # Send alert for significant changes
                if change_percent >= self.config.significant_change_percent:
                    await self.alert_manager.send_pricing_alert(
                        provider=provider,
                        model=model,
                        change_data=change,
                        severity="high"
                    )
                elif change_percent >= self.config.change_threshold_percent:
                    await self.alert_manager.send_pricing_alert(
                        provider=provider,
                        model=model,
                        change_data=change,
                        severity="medium"
                    )
        
        except Exception as e:
            logger.error(f"Error checking for pricing alerts: {e}")
    
    async def get_current_pricing(
        self,
        provider: str,
        model: str,
        force_refresh: bool = False
    ) -> Optional[Dict[str, float]]:
        """Get current pricing for a model."""
        if not force_refresh:
            # Try cache first
            cached_pricing = await self.cache.get_pricing(provider, model)
            if cached_pricing:
                return cached_pricing
        
        # Fetch from API if not cached or force refresh
        if provider in self.provider_apis:
            try:
                api = self.provider_apis[provider]
                pricing = await api.get_model_pricing(model)
                
                if pricing:
                    # Update cache
                    await self.cache.set_pricing(provider, model, pricing)
                    return pricing
            
            except Exception as e:
                logger.error(f"Failed to get pricing for {provider}:{model}: {e}")
        
        return None
    
    async def get_all_current_pricing(self, force_refresh: bool = False) -> Dict[str, Dict[str, Dict[str, float]]]:
        """Get current pricing for all models."""
        all_pricing = {}
        
        for provider_name in self.provider_apis:
            if provider_name in PROVIDER_MODEL_MAPPINGS:
                all_pricing[provider_name] = {}
                models = list(PROVIDER_MODEL_MAPPINGS[provider_name].keys())
                
                for model in models:
                    pricing = await self.get_current_pricing(provider_name, model, force_refresh)
                    if pricing:
                        all_pricing[provider_name][model] = pricing
        
        return all_pricing
    
    async def get_stale_pricing_report(self) -> Dict[str, Any]:
        """Get report of stale pricing data."""
        stale_items = await self.cache.get_stale_pricing(self.config.staleness_threshold_seconds)
        
        return {
            "stale_count": len(stale_items),
            "staleness_threshold_seconds": self.config.staleness_threshold_seconds,
            "stale_items": [
                {
                    "provider": provider,
                    "model": model,
                    "age_seconds": age_seconds,
                    "age_hours": age_seconds / 3600
                }
                for provider, model, age_seconds in stale_items
            ]
        }
    
    async def get_pricing_changes_report(
        self,
        since_hours: int = 24
    ) -> Dict[str, Any]:
        """Get report of pricing changes."""
        since_timestamp = time.time() - (since_hours * 3600)
        changes = await self.cache.get_pricing_changes(since_timestamp=since_timestamp)
        
        # Group changes by significance
        significant_changes = [c for c in changes if abs(c.get("change_percent", 0)) >= self.config.significant_change_percent]
        moderate_changes = [c for c in changes if self.config.change_threshold_percent <= abs(c.get("change_percent", 0)) < self.config.significant_change_percent]
        
        return {
            "period_hours": since_hours,
            "total_changes": len(changes),
            "significant_changes": len(significant_changes),
            "moderate_changes": len(moderate_changes),
            "changes": changes,
            "significant_changes_detail": significant_changes
        }
    
    async def validate_pricing_accuracy(
        self,
        provider: str,
        model: str,
        actual_cost: float,
        tokens_used: int,
        token_type: str = "input"
    ) -> Dict[str, Any]:
        """Validate pricing accuracy against actual usage."""
        if not self.config.validation_enabled:
            return {"validation_enabled": False}
        
        try:
            # Get current pricing
            pricing = await self.get_current_pricing(provider, model)
            if not pricing:
                return {"error": "No pricing data available"}
            
            # Calculate expected cost
            cost_per_token = pricing.get(token_type, 0.0) / 1000  # Convert from per-1K to per-token
            expected_cost = cost_per_token * tokens_used
            
            # Calculate variance
            if expected_cost > 0:
                variance_percent = ((actual_cost - expected_cost) / expected_cost) * 100
            else:
                variance_percent = 0.0
            
            # Check if within tolerance
            within_tolerance = abs(variance_percent) <= self.config.validation_tolerance_percent
            
            validation_result = {
                "provider": provider,
                "model": model,
                "token_type": token_type,
                "tokens_used": tokens_used,
                "expected_cost": expected_cost,
                "actual_cost": actual_cost,
                "variance_percent": variance_percent,
                "within_tolerance": within_tolerance,
                "tolerance_percent": self.config.validation_tolerance_percent,
                "validated_at": time.time()
            }
            
            # Send alert if variance is too high
            if not within_tolerance and self.alert_manager:
                await self.alert_manager.send_validation_alert(validation_result)
            
            return validation_result
        
        except Exception as e:
            logger.error(f"Error validating pricing accuracy: {e}")
            return {"error": str(e)}
    
    def get_monitoring_statistics(self) -> Dict[str, Any]:
        """Get monitoring statistics."""
        return {
            "is_monitoring": self._is_monitoring,
            "providers_configured": len(self.provider_apis),
            "update_count": self._update_count,
            "error_count": self._error_count,
            "change_count": self._change_count,
            "last_update_times": dict(self._last_update_times),
            "config": {
                "enabled": self.config.enabled,
                "update_interval_seconds": self.config.update_interval_seconds,
                "staleness_threshold_seconds": self.config.staleness_threshold_seconds,
                "change_detection_enabled": self.config.change_detection_enabled,
                "validation_enabled": self.config.validation_enabled
            }
        }