"""Main cost optimization engine that coordinates all optimization components."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .optimization_config import OptimizationConfig
from .budget_manager import BudgetManager
from .cost_forecaster import CostForecaster
from .anomaly_detector import CostAnomalyDetector
from ..pricing import get_pricing_manager

logger = logging.getLogger(__name__)


class CostOptimizer:
    """Main cost optimization engine coordinating all optimization components."""
    
    def __init__(self, config: Optional[OptimizationConfig] = None):
        self.config = config or OptimizationConfig.from_environment()
        
        # Initialize components
        self.budget_manager = BudgetManager(self.config)
        self.cost_forecaster = CostForecaster(self.config)
        self.anomaly_detector = CostAnomalyDetector(self.config)
        
        # Integration with pricing system
        self.pricing_manager = get_pricing_manager()
        
        # Optimization state
        self._optimization_task: Optional[asyncio.Task] = None
        self._is_optimizing = False
        
        # Optimization results cache
        self._optimization_results: Dict[str, Any] = {}
        self._last_optimization_time = 0.0
        
        # Performance tracking
        self._optimization_count = 0
        self._total_savings_identified = 0.0
        self._recommendations_generated = 0
        
        logger.info("Cost optimizer initialized")
    
    async def start_optimization(self) -> None:
        """Start the continuous cost optimization process."""
        if self._is_optimizing:
            logger.warning("Cost optimization is already running")
            return
        
        if not self.config.enabled:
            logger.info("Cost optimization is disabled")
            return
        
        self._is_optimizing = True
        self._optimization_task = asyncio.create_task(self._optimization_loop())
        logger.info("Cost optimization started")
    
    async def stop_optimization(self) -> None:
        """Stop the cost optimization process."""
        self._is_optimizing = False
        
        if self._optimization_task and not self._optimization_task.done():
            self._optimization_task.cancel()
            try:
                await self._optimization_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Cost optimization stopped")
    
    async def _optimization_loop(self) -> None:
        """Main optimization loop."""
        while self._is_optimizing:
            try:
                await self._run_optimization_cycle()
                await asyncio.sleep(self.config.optimization_interval_seconds)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in optimization loop: {e}")
                await asyncio.sleep(min(self.config.optimization_interval_seconds, 60))
    
    async def _run_optimization_cycle(self) -> None:
        """Run a single optimization cycle."""
        current_time = time.time()
        
        try:
            # 1. Detect anomalies
            if self.config.anomaly_detection_enabled:
                anomalies = self.anomaly_detector.detect_anomalies()
                if anomalies:
                    await self._handle_anomalies(anomalies)
            
            # 2. Generate cost forecasts
            if self.config.forecasting_enabled:
                forecast = self.cost_forecaster.forecast_cost(
                    horizon_hours=24,
                    model_type=self.config.forecasting_model_type
                )
                if "error" not in forecast:
                    await self._handle_forecast(forecast)
            
            # 3. Generate optimization recommendations
            recommendations = await self._generate_optimization_recommendations()
            if recommendations:
                await self._handle_recommendations(recommendations)
            
            # 4. Update optimization results
            self._optimization_results = {
                "last_optimization_time": current_time,
                "optimization_count": self._optimization_count,
                "total_savings_identified": self._total_savings_identified,
                "recommendations_generated": self._recommendations_generated
            }
            
            self._optimization_count += 1
            self._last_optimization_time = current_time
            
            logger.debug("Optimization cycle completed")
        
        except Exception as e:
            logger.error(f"Error in optimization cycle: {e}")
    
    async def _handle_anomalies(self, anomalies: List[Dict[str, Any]]) -> None:
        """Handle detected cost anomalies."""
        high_severity_anomalies = [a for a in anomalies if a["severity"] == "high"]
        
        if high_severity_anomalies:
            logger.warning(f"Detected {len(high_severity_anomalies)} high-severity cost anomalies")
            
            # Send alerts for high-severity anomalies
            for anomaly in high_severity_anomalies:
                await self._send_anomaly_alert(anomaly)
        
        # Log all anomalies for analysis
        logger.info(f"Detected {len(anomalies)} cost anomalies in current cycle")
    
    async def _handle_forecast(self, forecast: Dict[str, Any]) -> None:
        """Handle cost forecast results."""
        total_forecast = forecast.get("total_forecast_usd", 0)
        
        # Check if forecast exceeds budget thresholds
        if total_forecast > 0:
            # This would integrate with budget manager to check against limits
            logger.debug(f"24-hour cost forecast: ${total_forecast:.2f}")
    
    async def _handle_recommendations(self, recommendations: List[Dict[str, Any]]) -> None:
        """Handle optimization recommendations."""
        if not recommendations:
            return
        
        total_potential_savings = sum(
            rec.get("potential_savings_usd", 0) for rec in recommendations
        )
        
        self._total_savings_identified += total_potential_savings
        self._recommendations_generated += len(recommendations)
        
        logger.info(f"Generated {len(recommendations)} optimization recommendations with ${total_potential_savings:.2f} potential savings")
    
    async def _generate_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Generate cost optimization recommendations."""
        recommendations = []
        
        try:
            # Get current pricing data
            all_pricing = await self.pricing_manager.get_all_pricing()
            
            if not all_pricing:
                return recommendations
            
            # 1. Model substitution recommendations
            model_recommendations = await self._generate_model_substitution_recommendations(all_pricing)
            recommendations.extend(model_recommendations)
            
            # 2. Usage pattern optimization
            usage_recommendations = await self._generate_usage_optimization_recommendations()
            recommendations.extend(usage_recommendations)
            
            # 3. Budget optimization recommendations
            budget_recommendations = await self._generate_budget_optimization_recommendations()
            recommendations.extend(budget_recommendations)
            
            return recommendations
        
        except Exception as e:
            logger.error(f"Error generating optimization recommendations: {e}")
            return []
    
    async def _generate_model_substitution_recommendations(
        self,
        all_pricing: Dict[str, Dict[str, Dict[str, float]]]
    ) -> List[Dict[str, Any]]:
        """Generate recommendations for model substitutions."""
        recommendations = []
        
        # This would analyze current usage patterns and suggest cheaper alternatives
        # For now, we'll create a simplified version
        
        try:
            # Get usage data from cost aggregator
            from ..cost_aggregator import ENHANCED_COST
            snapshot = ENHANCED_COST.enhanced_snapshot()
            
            model_costs = snapshot.get("model_costs", {})
            token_usage = snapshot.get("token_usage", {}).get("by_model", {})
            
            for model, cost in model_costs.items():
                if cost < 1.0:  # Skip low-cost models
                    continue
                
                # Find cheaper alternatives
                alternatives = await self._find_cheaper_alternatives(model, all_pricing)
                
                if alternatives:
                    best_alternative = alternatives[0]
                    potential_savings = cost * (1 - best_alternative["cost_ratio"])
                    
                    if potential_savings >= (cost * self.config.cost_savings_threshold_percent / 100):
                        recommendations.append({
                            "type": "model_substitution",
                            "current_model": model,
                            "recommended_model": best_alternative["model"],
                            "current_cost_usd": cost,
                            "recommended_cost_usd": cost * best_alternative["cost_ratio"],
                            "potential_savings_usd": potential_savings,
                            "savings_percent": (1 - best_alternative["cost_ratio"]) * 100,
                            "quality_impact": best_alternative.get("quality_impact", "unknown"),
                            "confidence": "medium",
                            "implementation_effort": "low"
                        })
        
        except Exception as e:
            logger.error(f"Error generating model substitution recommendations: {e}")
        
        return recommendations
    
    async def _find_cheaper_alternatives(
        self,
        current_model: str,
        all_pricing: Dict[str, Dict[str, Dict[str, float]]]
    ) -> List[Dict[str, Any]]:
        """Find cheaper alternative models."""
        alternatives = []
        
        # Get current model pricing
        current_pricing = None
        current_provider = None
        
        for provider, models in all_pricing.items():
            if current_model in models:
                current_pricing = models[current_model]
                current_provider = provider
                break
        
        if not current_pricing:
            return alternatives
        
        current_input_cost = current_pricing.get("input", 0)
        current_output_cost = current_pricing.get("output", 0)
        
        # Find alternatives with lower cost
        for provider, models in all_pricing.items():
            for model, pricing in models.items():
                if model == current_model:
                    continue
                
                alt_input_cost = pricing.get("input", 0)
                alt_output_cost = pricing.get("output", 0)
                
                # Calculate cost ratio (alternative / current)
                if current_input_cost > 0 and current_output_cost > 0:
                    input_ratio = alt_input_cost / current_input_cost
                    output_ratio = alt_output_cost / current_output_cost
                    avg_ratio = (input_ratio + output_ratio) / 2
                    
                    if avg_ratio < 1.0:  # Cheaper alternative
                        alternatives.append({
                            "provider": provider,
                            "model": model,
                            "cost_ratio": avg_ratio,
                            "input_cost_ratio": input_ratio,
                            "output_cost_ratio": output_ratio,
                            "quality_impact": self._estimate_quality_impact(current_model, model)
                        })
        
        # Sort by cost ratio (cheapest first)
        alternatives.sort(key=lambda x: x["cost_ratio"])
        
        return alternatives[:5]  # Return top 5 alternatives
    
    def _estimate_quality_impact(self, current_model: str, alternative_model: str) -> str:
        """Estimate quality impact of switching models."""
        # This is a simplified heuristic - in practice, this would use
        # quality scores from the model registry or benchmarking data
        
        model_tiers = {
            "gpt-4": 5,
            "claude-3-opus": 5,
            "gpt-3.5-turbo": 3,
            "claude-3-sonnet": 4,
            "claude-3-haiku": 2,
            "gemini-pro": 3
        }
        
        current_tier = model_tiers.get(current_model.lower(), 3)
        alt_tier = model_tiers.get(alternative_model.lower(), 3)
        
        if alt_tier >= current_tier:
            return "minimal"
        elif alt_tier >= current_tier - 1:
            return "low"
        else:
            return "medium"
    
    async def _generate_usage_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Generate usage pattern optimization recommendations."""
        recommendations = []
        
        try:
            # Analyze usage patterns for optimization opportunities
            usage_forecast = self.cost_forecaster.get_usage_forecast(horizon_hours=24)
            
            if "error" not in usage_forecast:
                total_forecast_tokens = usage_forecast.get("total_forecast_tokens", 0)
                
                if total_forecast_tokens > 100000:  # High usage threshold
                    recommendations.append({
                        "type": "usage_optimization",
                        "recommendation": "Consider implementing request batching",
                        "description": f"Forecasted {total_forecast_tokens:,} tokens in next 24h. Batching could reduce costs by 10-15%",
                        "potential_savings_percent": 12.5,
                        "implementation_effort": "medium",
                        "confidence": "medium"
                    })
        
        except Exception as e:
            logger.error(f"Error generating usage optimization recommendations: {e}")
        
        return recommendations
    
    async def _generate_budget_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Generate budget-related optimization recommendations."""
        recommendations = []
        
        try:
            # Get budget status
            budget_status = await self.budget_manager.get_budget_status()
            
            # Check for tenants approaching budget limits
            for tenant_id, status in budget_status.get("tenant_status", {}).items():
                usage_percent = status.get("usage_percent", 0)
                
                if usage_percent > 70:  # Approaching budget limit
                    recommendations.append({
                        "type": "budget_optimization",
                        "tenant_id": tenant_id,
                        "recommendation": "Implement cost controls",
                        "description": f"Tenant {tenant_id} has used {usage_percent:.1f}% of budget",
                        "urgency": "high" if usage_percent > 90 else "medium",
                        "suggested_actions": [
                            "Enable request throttling",
                            "Switch to cheaper models for non-critical requests",
                            "Implement request prioritization"
                        ]
                    })
        
        except Exception as e:
            logger.error(f"Error generating budget optimization recommendations: {e}")
        
        return recommendations
    
    async def _send_anomaly_alert(self, anomaly: Dict[str, Any]) -> None:
        """Send alert for detected anomaly."""
        # This would integrate with the alerting system
        logger.warning(f"Cost anomaly alert: {anomaly['description']}")
    
    async def optimize_request(
        self,
        provider: str,
        model: str,
        estimated_cost: float,
        tokens: int,
        tenant_id: Optional[str] = None,
        quality_requirement: str = "balanced"
    ) -> Dict[str, Any]:
        """Optimize a specific request before processing."""
        optimization_result = {
            "original_request": {
                "provider": provider,
                "model": model,
                "estimated_cost": estimated_cost,
                "tokens": tokens
            },
            "optimized_request": None,
            "optimization_applied": False,
            "potential_savings": 0.0,
            "recommendations": []
        }
        
        try:
            # 1. Check if request is anomalous
            anomaly_check = self.anomaly_detector.is_anomalous_request(
                estimated_cost, tokens, provider, model, tenant_id
            )
            
            if anomaly_check["is_anomalous"]:
                optimization_result["recommendations"].append({
                    "type": "anomaly_warning",
                    "message": "Request appears anomalous based on historical patterns",
                    "confidence": anomaly_check["confidence"]
                })
            
            # 2. Check budget constraints
            budget_check = await self.budget_manager.check_request_allowed(
                tenant_id=tenant_id,
                estimated_cost=estimated_cost
            )
            
            if not budget_check["allowed"]:
                optimization_result["recommendations"].append({
                    "type": "budget_constraint",
                    "message": "Request blocked or throttled due to budget limits",
                    "reasons": budget_check["reasons"],
                    "throttle_factor": budget_check.get("throttle_factor", 1.0)
                })
                return optimization_result
            
            # 3. Find cheaper alternatives if cost optimization is the target
            if self.config.optimization_target in ["cost", "balanced"]:
                all_pricing = await self.pricing_manager.get_all_pricing()
                alternatives = await self._find_cheaper_alternatives(model, all_pricing)
                
                if alternatives:
                    best_alternative = alternatives[0]
                    savings_percent = (1 - best_alternative["cost_ratio"]) * 100
                    
                    if savings_percent >= self.config.cost_savings_threshold_percent:
                        quality_impact = best_alternative.get("quality_impact", "unknown")
                        
                        # Apply optimization if quality impact is acceptable
                        if (quality_requirement == "cost" or 
                            (quality_requirement == "balanced" and quality_impact in ["minimal", "low"])):
                            
                            optimized_cost = estimated_cost * best_alternative["cost_ratio"]
                            
                            optimization_result.update({
                                "optimized_request": {
                                    "provider": best_alternative["provider"],
                                    "model": best_alternative["model"],
                                    "estimated_cost": optimized_cost,
                                    "tokens": tokens
                                },
                                "optimization_applied": True,
                                "potential_savings": estimated_cost - optimized_cost,
                                "savings_percent": savings_percent,
                                "quality_impact": quality_impact
                            })
                        else:
                            optimization_result["recommendations"].append({
                                "type": "cost_optimization",
                                "message": f"Could save {savings_percent:.1f}% by switching to {best_alternative['model']}",
                                "quality_impact": quality_impact,
                                "potential_savings": estimated_cost * (1 - best_alternative["cost_ratio"])
                            })
            
            return optimization_result
        
        except Exception as e:
            logger.error(f"Error optimizing request: {e}")
            optimization_result["error"] = str(e)
            return optimization_result
    
    async def get_optimization_dashboard(self) -> Dict[str, Any]:
        """Get comprehensive optimization dashboard data."""
        current_time = time.time()
        
        dashboard = {
            "overview": {
                "optimization_enabled": self.config.enabled,
                "last_optimization": self._last_optimization_time,
                "optimization_count": self._optimization_count,
                "total_savings_identified": self._total_savings_identified,
                "recommendations_generated": self._recommendations_generated
            },
            "budget_status": await self.budget_manager.get_budget_status(),
            "anomaly_summary": self.anomaly_detector.get_anomaly_summary(hours=24),
            "cost_forecast": {},
            "recent_recommendations": [],
            "system_health": {
                "budget_manager": "healthy",
                "cost_forecaster": "healthy",
                "anomaly_detector": "healthy"
            }
        }
        
        # Add cost forecast if available
        try:
            forecast = self.cost_forecaster.forecast_cost(horizon_hours=24)
            if "error" not in forecast:
                dashboard["cost_forecast"] = forecast
        except Exception as e:
            dashboard["cost_forecast"] = {"error": str(e)}
        
        # Add recent recommendations
        try:
            recent_recommendations = await self._generate_optimization_recommendations()
            dashboard["recent_recommendations"] = recent_recommendations[:10]  # Top 10
        except Exception as e:
            dashboard["recent_recommendations"] = {"error": str(e)}
        
        dashboard["generated_at"] = current_time
        return dashboard


# Global cost optimizer instance
_cost_optimizer: Optional[CostOptimizer] = None


def get_cost_optimizer() -> CostOptimizer:
    """Get the global cost optimizer instance."""
    global _cost_optimizer
    if _cost_optimizer is None:
        _cost_optimizer = CostOptimizer()
    return _cost_optimizer