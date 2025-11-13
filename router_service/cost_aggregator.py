"""Enhanced cost aggregation with real-time pricing integration (GAP-063).

Maintains cumulative USD cost per QoS and provides helper to export metrics.
Now integrated with real-time pricing monitoring system.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from metrics.registry import REGISTRY

logger = logging.getLogger(__name__)


class EnhancedCostAggregator:
    """Enhanced cost aggregator with real-time pricing integration."""
    
    def __init__(self) -> None:
        # Legacy QoS-based tracking
        self._usd_by_qos: dict[str, float] = {"gold": 0.0, "silver": 0.0, "bronze": 0.0}
        self._usd_by_adapter: dict[str, dict[str, float]] = {}  # adapter_id -> {qos: cost}
        
        # Enhanced tracking by provider and model
        self._usd_by_provider: dict[str, float] = {}  # provider -> total_cost
        self._usd_by_model: dict[str, float] = {}     # model -> total_cost
        self._usd_by_tenant: dict[str, float] = {}    # tenant_id -> total_cost
        
        # Token usage tracking
        self._tokens_by_provider: dict[str, dict[str, int]] = {}  # provider -> {input: count, output: count}
        self._tokens_by_model: dict[str, dict[str, int]] = {}     # model -> {input: count, output: count}
        
        # Request tracking
        self._requests_by_provider: dict[str, int] = {}
        self._requests_by_model: dict[str, int] = {}
        
        # Pricing validation tracking
        self._pricing_validation_errors = 0
        self._pricing_validation_total = 0
        
        # Real-time pricing integration
        self._pricing_manager = None
        self._pricing_integration_enabled = True
    
    def _get_pricing_manager(self):
        """Lazy initialization of pricing manager to avoid circular imports."""
        if self._pricing_manager is None and self._pricing_integration_enabled:
            try:
                from .pricing import get_pricing_manager
                self._pricing_manager = get_pricing_manager()
            except ImportError:
                logger.warning("Pricing manager not available, using legacy cost tracking")
                self._pricing_integration_enabled = False
        return self._pricing_manager
    
    def record(self, qos: str, usd: float, adapter_id: str = None) -> None:
        """Legacy method for QoS-based cost recording."""
        q = qos.lower()
        if q not in self._usd_by_qos:
            self._usd_by_qos[q] = 0.0
        self._usd_by_qos[q] += max(0.0, float(usd))
        
        # Update per-QoS counters (POC: separate names)
        REGISTRY.counter(f"cost_usd_total_qos_{q}").inc(
            int(self._usd_by_qos[q] * 1_000_000) - REGISTRY.counter(f"cost_usd_total_qos_{q}").value
        )

        # Track per-adapter costs if adapter_id provided
        if adapter_id:
            if adapter_id not in self._usd_by_adapter:
                self._usd_by_adapter[adapter_id] = {"gold": 0.0, "silver": 0.0, "bronze": 0.0}
            if q not in self._usd_by_adapter[adapter_id]:
                self._usd_by_adapter[adapter_id][q] = 0.0
            self._usd_by_adapter[adapter_id][q] += max(0.0, float(usd))
    
    async def record_request_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        actual_cost: Optional[float] = None,
        tenant_id: Optional[str] = None,
        qos: str = "silver",
        adapter_id: Optional[str] = None,
        validate_pricing: bool = True
    ) -> Dict[str, Any]:
        """Enhanced method for recording request costs with real-time pricing."""
        try:
            # Get pricing manager
            pricing_manager = self._get_pricing_manager()
            
            # Calculate expected cost using real-time pricing
            expected_cost_result = None
            if pricing_manager:
                expected_cost_result = await pricing_manager.calculate_request_cost(
                    provider=provider,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens
                )
            
            # Use actual cost if provided, otherwise use calculated cost
            if actual_cost is not None:
                final_cost = actual_cost
            elif expected_cost_result and "total_cost_usd" in expected_cost_result:
                final_cost = expected_cost_result["total_cost_usd"]
            else:
                # Fallback to legacy estimation
                final_cost = self._estimate_cost_legacy(provider, model, input_tokens, output_tokens)
            
            # Record costs in various dimensions
            self._record_provider_cost(provider, final_cost)
            self._record_model_cost(model, final_cost)
            
            if tenant_id:
                self._record_tenant_cost(tenant_id, final_cost)
            
            # Record token usage
            self._record_token_usage(provider, model, input_tokens, output_tokens)
            
            # Record request count
            self._record_request_count(provider, model)
            
            # Legacy QoS recording
            self.record(qos, final_cost, adapter_id)
            
            # Validate pricing if enabled and actual cost provided
            validation_result = None
            if validate_pricing and actual_cost is not None and pricing_manager:
                validation_result = await pricing_manager.validate_actual_cost(
                    provider=provider,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    actual_cost=actual_cost
                )
                
                self._pricing_validation_total += 1
                if validation_result and not validation_result.get("within_tolerance", True):
                    self._pricing_validation_errors += 1
            
            # Update metrics
            self._update_enhanced_metrics()
            
            return {
                "provider": provider,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "final_cost_usd": final_cost,
                "expected_cost_result": expected_cost_result,
                "validation_result": validation_result,
                "tenant_id": tenant_id
            }
        
        except Exception as e:
            logger.error(f"Error recording request cost: {e}")
            # Fallback to legacy recording
            fallback_cost = self._estimate_cost_legacy(provider, model, input_tokens, output_tokens)
            self.record(qos, fallback_cost, adapter_id)
            return {"error": str(e), "fallback_cost_usd": fallback_cost}
    
    def _record_provider_cost(self, provider: str, cost: float) -> None:
        """Record cost by provider."""
        if provider not in self._usd_by_provider:
            self._usd_by_provider[provider] = 0.0
        self._usd_by_provider[provider] += cost
    
    def _record_model_cost(self, model: str, cost: float) -> None:
        """Record cost by model."""
        if model not in self._usd_by_model:
            self._usd_by_model[model] = 0.0
        self._usd_by_model[model] += cost
    
    def _record_tenant_cost(self, tenant_id: str, cost: float) -> None:
        """Record cost by tenant."""
        if tenant_id not in self._usd_by_tenant:
            self._usd_by_tenant[tenant_id] = 0.0
        self._usd_by_tenant[tenant_id] += cost
    
    def _record_token_usage(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> None:
        """Record token usage by provider and model."""
        # By provider
        if provider not in self._tokens_by_provider:
            self._tokens_by_provider[provider] = {"input": 0, "output": 0}
        self._tokens_by_provider[provider]["input"] += input_tokens
        self._tokens_by_provider[provider]["output"] += output_tokens
        
        # By model
        if model not in self._tokens_by_model:
            self._tokens_by_model[model] = {"input": 0, "output": 0}
        self._tokens_by_model[model]["input"] += input_tokens
        self._tokens_by_model[model]["output"] += output_tokens
    
    def _record_request_count(self, provider: str, model: str) -> None:
        """Record request counts."""
        self._requests_by_provider[provider] = self._requests_by_provider.get(provider, 0) + 1
        self._requests_by_model[model] = self._requests_by_model.get(model, 0) + 1
    
    def _estimate_cost_legacy(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """Legacy cost estimation when real-time pricing is not available."""
        # Simple fallback pricing (should be replaced with real-time pricing)
        fallback_rates = {
            "openai": {"input": 0.01, "output": 0.03},
            "anthropic": {"input": 0.008, "output": 0.024},
            "google": {"input": 0.001, "output": 0.001}
        }
        
        provider_rates = fallback_rates.get(provider, {"input": 0.01, "output": 0.03})
        
        input_cost = (input_tokens / 1000.0) * provider_rates["input"]
        output_cost = (output_tokens / 1000.0) * provider_rates["output"]
        
        return input_cost + output_cost
    
    def _update_enhanced_metrics(self) -> None:
        """Update enhanced metrics in the registry."""
        # Provider costs
        for provider, cost in self._usd_by_provider.items():
            REGISTRY.counter(f"cost_usd_total_provider_{provider}").set(int(cost * 1_000_000))
        
        # Model costs
        for model, cost in self._usd_by_model.items():
            # Sanitize model name for metrics
            safe_model = model.replace("-", "_").replace(".", "_")
            REGISTRY.counter(f"cost_usd_total_model_{safe_model}").set(int(cost * 1_000_000))
        
        # Token usage
        total_input_tokens = sum(tokens["input"] for tokens in self._tokens_by_provider.values())
        total_output_tokens = sum(tokens["output"] for tokens in self._tokens_by_provider.values())
        
        REGISTRY.counter("tokens_input_total").set(total_input_tokens)
        REGISTRY.counter("tokens_output_total").set(total_output_tokens)
        
        # Request counts
        total_requests = sum(self._requests_by_provider.values())
        REGISTRY.counter("requests_total_enhanced").set(total_requests)
        
        # Pricing validation metrics
        if self._pricing_validation_total > 0:
            validation_error_rate = self._pricing_validation_errors / self._pricing_validation_total
            REGISTRY.gauge("pricing_validation_error_rate").set(validation_error_rate)
    
    def snapshot(self) -> dict[str, float]:
        """Legacy snapshot method."""
        return dict(self._usd_by_qos)

    def snapshot_by_adapter(self) -> dict[str, dict[str, float]]:
        """Legacy snapshot by adapter method."""
        return {adapter_id: dict(costs) for adapter_id, costs in self._usd_by_adapter.items()}
    
    def enhanced_snapshot(self) -> Dict[str, Any]:
        """Enhanced snapshot with all cost dimensions."""
        return {
            "qos_costs": dict(self._usd_by_qos),
            "provider_costs": dict(self._usd_by_provider),
            "model_costs": dict(self._usd_by_model),
            "tenant_costs": dict(self._usd_by_tenant),
            "token_usage": {
                "by_provider": dict(self._tokens_by_provider),
                "by_model": dict(self._tokens_by_model)
            },
            "request_counts": {
                "by_provider": dict(self._requests_by_provider),
                "by_model": dict(self._requests_by_model)
            },
            "pricing_validation": {
                "total_validations": self._pricing_validation_total,
                "validation_errors": self._pricing_validation_errors,
                "error_rate": (
                    self._pricing_validation_errors / self._pricing_validation_total
                    if self._pricing_validation_total > 0 else 0.0
                )
            }
        }
    
    async def get_cost_optimization_insights(self) -> Dict[str, Any]:
        """Get cost optimization insights based on usage patterns."""
        insights = {
            "top_cost_providers": [],
            "top_cost_models": [],
            "cost_efficiency": {},
            "recommendations": []
        }
        
        try:
            # Top cost providers
            sorted_providers = sorted(
                self._usd_by_provider.items(),
                key=lambda x: x[1],
                reverse=True
            )
            insights["top_cost_providers"] = [
                {"provider": provider, "cost_usd": cost}
                for provider, cost in sorted_providers[:5]
            ]
            
            # Top cost models
            sorted_models = sorted(
                self._usd_by_model.items(),
                key=lambda x: x[1],
                reverse=True
            )
            insights["top_cost_models"] = [
                {"model": model, "cost_usd": cost}
                for model, cost in sorted_models[:5]
            ]
            
            # Cost efficiency (cost per token)
            for model, cost in self._usd_by_model.items():
                if model in self._tokens_by_model:
                    total_tokens = (
                        self._tokens_by_model[model]["input"] +
                        self._tokens_by_model[model]["output"]
                    )
                    if total_tokens > 0:
                        cost_per_token = cost / total_tokens
                        insights["cost_efficiency"][model] = {
                            "cost_per_token": cost_per_token,
                            "total_cost": cost,
                            "total_tokens": total_tokens
                        }
            
            # Get recommendations from pricing manager
            pricing_manager = self._get_pricing_manager()
            if pricing_manager:
                # Convert usage data to format expected by pricing manager
                usage_data = {}
                for provider, tokens in self._tokens_by_provider.items():
                    usage_data[provider] = {}
                    for model, model_tokens in self._tokens_by_model.items():
                        # Simple heuristic to associate models with providers
                        if any(p in model.lower() for p in [provider.lower()]):
                            usage_data[provider][model] = model_tokens["input"] + model_tokens["output"]
                
                recommendations = await pricing_manager.get_cost_optimization_recommendations(usage_data)
                insights["recommendations"] = recommendations
        
        except Exception as e:
            logger.error(f"Error generating cost optimization insights: {e}")
            insights["error"] = str(e)
        
        return insights


# Maintain backward compatibility
class CostAggregator(EnhancedCostAggregator):
    """Legacy wrapper for backward compatibility."""
    pass


# Global instances
GLOBAL_COST = EnhancedCostAggregator()
ENHANCED_COST = GLOBAL_COST  # Alias for enhanced features
