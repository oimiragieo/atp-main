"""Pricing data caching with TTL and change detection."""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from ..cache import get_cache_manager

logger = logging.getLogger(__name__)


class PricingCache:
    """Cache for pricing data with change detection and TTL management."""
    
    def __init__(self, ttl_seconds: int = 1800, cache_prefix: str = "pricing:"):
        self.ttl_seconds = ttl_seconds
        self.cache_prefix = cache_prefix
        self.cache_manager = get_cache_manager()
        
        # Change detection
        self._change_threshold = 0.01  # 1% change threshold
    
    def _make_key(self, provider: str, model: str, pricing_type: str = "current") -> str:
        """Create cache key for pricing data."""
        return f"{self.cache_prefix}{provider}:{model}:{pricing_type}"
    
    def _make_history_key(self, provider: str, model: str) -> str:
        """Create cache key for pricing history."""
        return f"{self.cache_prefix}history:{provider}:{model}"
    
    async def get_pricing(self, provider: str, model: str) -> Optional[Dict[str, float]]:
        """Get cached pricing data for a model."""
        cache_key = self._make_key(provider, model)
        
        try:
            cached_data = await self.cache_manager.get(cache_key)
            if cached_data:
                return cached_data.get("pricing")
        except Exception as e:
            logger.error(f"Failed to get cached pricing for {provider}:{model}: {e}")
        
        return None
    
    async def set_pricing(
        self,
        provider: str,
        model: str,
        pricing: Dict[str, float],
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Set pricing data in cache with change detection."""
        cache_key = self._make_key(provider, model)
        
        try:
            # Get previous pricing for change detection
            previous_data = await self.cache_manager.get(cache_key)
            previous_pricing = previous_data.get("pricing") if previous_data else None
            
            # Detect changes
            changes_detected = []
            if previous_pricing:
                changes_detected = self._detect_changes(previous_pricing, pricing)
            
            # Prepare cache data
            cache_data = {
                "pricing": pricing,
                "timestamp": time.time(),
                "provider": provider,
                "model": model,
                "metadata": metadata or {},
                "changes_detected": changes_detected
            }
            
            # Store in cache
            success = await self.cache_manager.set(cache_key, cache_data, self.ttl_seconds)
            
            # Update pricing history if changes detected
            if changes_detected:
                await self._update_pricing_history(provider, model, pricing, changes_detected)
            
            return success
        
        except Exception as e:
            logger.error(f"Failed to set cached pricing for {provider}:{model}: {e}")
            return False
    
    def _detect_changes(
        self,
        previous_pricing: Dict[str, float],
        current_pricing: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """Detect pricing changes between previous and current data."""
        changes = []
        
        for pricing_type in ["input", "output"]:
            prev_price = previous_pricing.get(pricing_type, 0.0)
            curr_price = current_pricing.get(pricing_type, 0.0)
            
            if prev_price > 0:  # Avoid division by zero
                change_percent = ((curr_price - prev_price) / prev_price) * 100
                
                if abs(change_percent) >= (self._change_threshold * 100):
                    changes.append({
                        "type": pricing_type,
                        "previous_price": prev_price,
                        "current_price": curr_price,
                        "change_percent": change_percent,
                        "change_absolute": curr_price - prev_price,
                        "detected_at": time.time()
                    })
        
        return changes
    
    async def _update_pricing_history(
        self,
        provider: str,
        model: str,
        pricing: Dict[str, float],
        changes: List[Dict[str, Any]]
    ) -> None:
        """Update pricing history with detected changes."""
        history_key = self._make_history_key(provider, model)
        
        try:
            # Get existing history
            history = await self.cache_manager.get(history_key) or []
            
            # Add new entry
            history_entry = {
                "timestamp": time.time(),
                "pricing": pricing,
                "changes": changes
            }
            
            history.append(history_entry)
            
            # Keep only last 100 entries
            if len(history) > 100:
                history = history[-100:]
            
            # Store updated history (longer TTL for history)
            await self.cache_manager.set(history_key, history, self.ttl_seconds * 24)  # 24x longer TTL
        
        except Exception as e:
            logger.error(f"Failed to update pricing history for {provider}:{model}: {e}")
    
    async def get_pricing_history(
        self,
        provider: str,
        model: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get pricing history for a model."""
        history_key = self._make_history_key(provider, model)
        
        try:
            history = await self.cache_manager.get(history_key) or []
            return history[-limit:] if limit else history
        except Exception as e:
            logger.error(f"Failed to get pricing history for {provider}:{model}: {e}")
            return []
    
    async def get_stale_pricing(self, staleness_threshold: int = 3600) -> List[Tuple[str, str, float]]:
        """Get list of stale pricing data (provider, model, age_seconds)."""
        stale_items = []
        current_time = time.time()
        
        try:
            # Get all pricing keys
            pricing_keys = await self.cache_manager.keys(f"{self.cache_prefix}*:*:current")
            
            for key in pricing_keys:
                try:
                    cached_data = await self.cache_manager.get(key)
                    if cached_data:
                        timestamp = cached_data.get("timestamp", 0)
                        age_seconds = current_time - timestamp
                        
                        if age_seconds > staleness_threshold:
                            provider = cached_data.get("provider", "unknown")
                            model = cached_data.get("model", "unknown")
                            stale_items.append((provider, model, age_seconds))
                
                except Exception as e:
                    logger.error(f"Failed to check staleness for key {key}: {e}")
        
        except Exception as e:
            logger.error(f"Failed to get stale pricing data: {e}")
        
        return stale_items
    
    async def get_pricing_changes(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        since_timestamp: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Get pricing changes with optional filtering."""
        changes = []
        
        try:
            # Determine which keys to check
            if provider and model:
                keys = [self._make_key(provider, model)]
            else:
                pattern = f"{self.cache_prefix}*:*:current"
                keys = await self.cache_manager.keys(pattern)
            
            for key in keys:
                try:
                    cached_data = await self.cache_manager.get(key)
                    if cached_data and cached_data.get("changes_detected"):
                        item_changes = cached_data["changes_detected"]
                        
                        # Filter by timestamp if provided
                        if since_timestamp:
                            item_changes = [
                                change for change in item_changes
                                if change.get("detected_at", 0) >= since_timestamp
                            ]
                        
                        if item_changes:
                            changes.extend([
                                {
                                    **change,
                                    "provider": cached_data.get("provider"),
                                    "model": cached_data.get("model")
                                }
                                for change in item_changes
                            ])
                
                except Exception as e:
                    logger.error(f"Failed to get changes for key {key}: {e}")
        
        except Exception as e:
            logger.error(f"Failed to get pricing changes: {e}")
        
        return changes
    
    async def clear_pricing_cache(self, provider: Optional[str] = None, model: Optional[str] = None) -> int:
        """Clear pricing cache with optional filtering."""
        try:
            if provider and model:
                # Clear specific model
                keys_to_clear = [
                    self._make_key(provider, model),
                    self._make_history_key(provider, model)
                ]
                cleared_count = 0
                for key in keys_to_clear:
                    if await self.cache_manager.delete(key):
                        cleared_count += 1
                return cleared_count
            
            elif provider:
                # Clear all models for provider
                pattern = f"{self.cache_prefix}{provider}:*"
                return await self.cache_manager.invalidate_pattern(pattern)
            
            else:
                # Clear all pricing data
                pattern = f"{self.cache_prefix}*"
                return await self.cache_manager.invalidate_pattern(pattern)
        
        except Exception as e:
            logger.error(f"Failed to clear pricing cache: {e}")
            return 0
    
    async def get_cache_statistics(self) -> Dict[str, Any]:
        """Get pricing cache statistics."""
        try:
            # Get all pricing keys
            current_keys = await self.cache_manager.keys(f"{self.cache_prefix}*:*:current")
            history_keys = await self.cache_manager.keys(f"{self.cache_prefix}history:*")
            
            # Count by provider
            provider_counts = {}
            stale_count = 0
            current_time = time.time()
            
            for key in current_keys:
                try:
                    cached_data = await self.cache_manager.get(key)
                    if cached_data:
                        provider = cached_data.get("provider", "unknown")
                        provider_counts[provider] = provider_counts.get(provider, 0) + 1
                        
                        # Check staleness
                        timestamp = cached_data.get("timestamp", 0)
                        if current_time - timestamp > self.ttl_seconds:
                            stale_count += 1
                
                except Exception:
                    pass
            
            return {
                "total_cached_models": len(current_keys),
                "history_entries": len(history_keys),
                "stale_entries": stale_count,
                "provider_counts": provider_counts,
                "cache_ttl_seconds": self.ttl_seconds
            }
        
        except Exception as e:
            logger.error(f"Failed to get cache statistics: {e}")
            return {}