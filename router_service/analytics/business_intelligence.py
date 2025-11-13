"""Business intelligence and strategic insights for enterprise AI platform."""

import asyncio
import logging
import statistics
import time
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class BusinessIntelligenceEngine:
    """Generates business intelligence insights and strategic recommendations."""
    
    def __init__(self, config):
        self.config = config
        
        # BI state
        self._insights_cache = {}
        self._last_analysis_time = 0
        self._historical_data = []
        
        # Business metrics tracking
        self._kpi_history = defaultdict(list)
        self._cost_trends = []
        self._usage_forecasts = {}
        
        logger.info("Business intelligence engine initialized")
    
    async def generate_business_insights(
        self,
        request_data: List[Dict[str, Any]],
        cost_data: List[Dict[str, Any]],
        performance_data: List[Dict[str, Any]],
        time_window_days: int = 30
    ) -> Dict[str, Any]:
        """Generate comprehensive business intelligence insights."""
        try:
            cutoff_time = time.time() - (time_window_days * 24 * 3600)
            
            # Filter data by time window
            recent_requests = [r for r in request_data if r.get("timestamp", 0) >= cutoff_time]
            recent_costs = [c for c in cost_data if c.get("timestamp", 0) >= cutoff_time]
            recent_performance = [p for p in performance_data if p.get("timestamp", 0) >= cutoff_time]
            
            insights = {
                "analysis_period": {
                    "days": time_window_days,
                    "start_date": datetime.fromtimestamp(cutoff_time).isoformat(),
                    "end_date": datetime.now().isoformat()
                },
                "data_summary": {
                    "total_requests": len(recent_requests),
                    "total_cost_entries": len(recent_costs),
                    "total_performance_entries": len(recent_performance)
                }
            }
            
            # Cost analysis and ROI
            if self.config.cost_analysis:
                insights["cost_analysis"] = await self._analyze_cost_trends(recent_costs, recent_requests)
            
            # Usage forecasting
            if self.config.usage_forecasting:
                insights["usage_forecast"] = await self._generate_usage_forecast(recent_requests)
            
            # Capacity planning
            if self.config.capacity_planning:
                insights["capacity_planning"] = await self._analyze_capacity_needs(recent_requests, recent_performance)
            
            # ROI analysis
            if self.config.roi_analysis:
                insights["roi_analysis"] = await self._calculate_roi_metrics(recent_requests, recent_costs)
            
            # Business KPIs
            insights["business_kpis"] = await self._calculate_business_kpis(recent_requests, recent_costs, recent_performance)
            
            # Strategic recommendations
            insights["strategic_recommendations"] = await self._generate_strategic_recommendations(insights)
            
            # Market analysis
            insights["market_analysis"] = await self._analyze_market_trends(recent_requests)
            
            # User behavior insights
            insights["user_behavior"] = await self._analyze_user_behavior_patterns(recent_requests)
            
            # Cache results
            self._insights_cache = insights
            self._last_analysis_time = time.time()
            
            return insights
        
        except Exception as e:
            logger.error(f"Error generating business insights: {e}")
            return {"error": str(e)}
    
    async def _analyze_cost_trends(self, cost_data: List[Dict[str, Any]], request_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze cost trends and spending patterns."""
        if not cost_data and not request_data:
            return {"error": "No cost data available"}
        
        # Extract cost information from both sources
        all_costs = []
        
        # From dedicated cost data
        for cost_entry in cost_data:
            all_costs.append({
                "timestamp": cost_entry.get("timestamp", time.time()),
                "cost_usd": cost_entry.get("cost_usd", 0),
                "model": cost_entry.get("model"),
                "provider": cost_entry.get("provider"),
                "tenant_id": cost_entry.get("tenant_id"),
                "user_id": cost_entry.get("user_id")
            })
        
        # From request data
        for request in request_data:
            if request.get("cost_usd"):
                all_costs.append({
                    "timestamp": request.get("timestamp", time.time()),
                    "cost_usd": request.get("cost_usd", 0),
                    "model": request.get("model_used"),
                    "provider": request.get("provider_used"),
                    "tenant_id": request.get("tenant_id"),
                    "user_id": request.get("user_id")
                })
        
        if not all_costs:
            return {"error": "No cost information available"}
        
        # Sort by timestamp
        all_costs.sort(key=lambda x: x["timestamp"])
        
        analysis = {
            "total_cost_usd": sum(c["cost_usd"] for c in all_costs),
            "cost_entries": len(all_costs),
            "average_cost_per_entry": statistics.mean(c["cost_usd"] for c in all_costs),
            "cost_range": {
                "min_usd": min(c["cost_usd"] for c in all_costs),
                "max_usd": max(c["cost_usd"] for c in all_costs)
            }
        }
        
        # Daily cost trends
        daily_costs = defaultdict(float)
        for cost_entry in all_costs:
            date_key = datetime.fromtimestamp(cost_entry["timestamp"]).strftime("%Y-%m-%d")
            daily_costs[date_key] += cost_entry["cost_usd"]
        
        if len(daily_costs) > 1:
            daily_values = list(daily_costs.values())
            analysis["daily_trends"] = {
                "daily_costs": dict(daily_costs),
                "average_daily_cost": statistics.mean(daily_values),
                "daily_cost_trend": self._calculate_trend_direction(daily_values),
                "cost_volatility": statistics.stdev(daily_values) if len(daily_values) > 1 else 0
            }
        
        # Cost by model
        model_costs = defaultdict(float)
        model_counts = defaultdict(int)
        for cost_entry in all_costs:
            model = cost_entry.get("model")
            if model:
                model_costs[model] += cost_entry["cost_usd"]
                model_counts[model] += 1
        
        if model_costs:
            analysis["cost_by_model"] = {
                "total_costs": dict(model_costs),
                "average_costs": {model: cost / model_counts[model] for model, cost in model_costs.items()},
                "most_expensive_model": max(model_costs.items(), key=lambda x: x[1])[0],
                "most_cost_effective_model": min(model_costs.items(), key=lambda x: x[1] / model_counts[x[0]])[0]
            }
        
        # Cost by provider
        provider_costs = defaultdict(float)
        for cost_entry in all_costs:
            provider = cost_entry.get("provider")
            if provider:
                provider_costs[provider] += cost_entry["cost_usd"]
        
        if provider_costs:
            analysis["cost_by_provider"] = dict(provider_costs)
        
        # Cost by tenant (for multi-tenant analysis)
        tenant_costs = defaultdict(float)
        for cost_entry in all_costs:
            tenant = cost_entry.get("tenant_id")
            if tenant:
                tenant_costs[tenant] += cost_entry["cost_usd"]
        
        if tenant_costs:
            analysis["cost_by_tenant"] = {
                "tenant_costs": dict(tenant_costs),
                "top_spending_tenants": dict(sorted(tenant_costs.items(), key=lambda x: x[1], reverse=True)[:10])
            }
        
        # Cost efficiency metrics
        if len(all_costs) > 1:
            # Calculate cost per request over time
            time_windows = self._create_time_windows_from_costs(all_costs, window_hours=24)
            cost_efficiency_trend = []
            
            for window in time_windows:
                if window:
                    window_cost = sum(c["cost_usd"] for c in window)
                    window_requests = len(window)
                    cost_per_request = window_cost / window_requests if window_requests > 0 else 0
                    
                    cost_efficiency_trend.append({
                        "timestamp": window[0]["timestamp"],
                        "cost_per_request": cost_per_request,
                        "total_cost": window_cost,
                        "request_count": window_requests
                    })
            
            if cost_efficiency_trend:
                analysis["cost_efficiency"] = {
                    "trend_data": cost_efficiency_trend,
                    "efficiency_trend": self._calculate_trend_direction([t["cost_per_request"] for t in cost_efficiency_trend])
                }
        
        return analysis
    
    async def _generate_usage_forecast(self, request_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate usage forecasting and demand predictions."""
        if len(request_data) < 7:  # Need at least a week of data
            return {"error": "Insufficient data for forecasting (minimum 7 days required)"}
        
        # Sort requests by timestamp
        sorted_requests = sorted(request_data, key=lambda x: x.get("timestamp", 0))
        
        # Group by day
        daily_usage = defaultdict(int)
        for request in sorted_requests:
            date_key = datetime.fromtimestamp(request.get("timestamp", time.time())).strftime("%Y-%m-%d")
            daily_usage[date_key] += 1
        
        if len(daily_usage) < 3:
            return {"error": "Insufficient daily data for forecasting"}
        
        daily_values = list(daily_usage.values())
        dates = list(daily_usage.keys())
        
        forecast = {
            "historical_data": {
                "daily_usage": dict(daily_usage),
                "analysis_period_days": len(daily_usage),
                "average_daily_requests": statistics.mean(daily_values),
                "peak_daily_requests": max(daily_values),
                "usage_trend": self._calculate_trend_direction(daily_values)
            }
        }
        
        # Simple linear forecast for next 30 days
        if len(daily_values) >= 7:
            # Calculate growth rate
            recent_avg = statistics.mean(daily_values[-7:])  # Last 7 days
            earlier_avg = statistics.mean(daily_values[:-7]) if len(daily_values) > 7 else recent_avg
            
            growth_rate = (recent_avg - earlier_avg) / earlier_avg if earlier_avg > 0 else 0
            
            # Generate forecast
            forecast_days = 30
            forecasted_usage = []
            
            for i in range(1, forecast_days + 1):
                base_usage = recent_avg
                projected_usage = base_usage * (1 + growth_rate * (i / 7))  # Weekly growth application
                
                # Add some seasonality (simple weekly pattern)
                day_of_week = (len(daily_values) + i - 1) % 7
                seasonal_multiplier = self._get_seasonal_multiplier(day_of_week, daily_values, dates)
                
                final_projection = max(0, projected_usage * seasonal_multiplier)
                
                forecasted_usage.append({
                    "day": i,
                    "projected_requests": int(final_projection),
                    "confidence": max(0.5, 1.0 - (i / forecast_days) * 0.5)  # Decreasing confidence
                })
            
            forecast["forecast"] = {
                "forecast_horizon_days": forecast_days,
                "growth_rate_weekly": growth_rate,
                "projected_usage": forecasted_usage,
                "total_projected_requests": sum(f["projected_requests"] for f in forecasted_usage),
                "average_projected_daily": statistics.mean(f["projected_requests"] for f in forecasted_usage)
            }
        
        # Model-specific forecasting
        model_usage = defaultdict(lambda: defaultdict(int))
        for request in sorted_requests:
            model = request.get("model_used")
            if model:
                date_key = datetime.fromtimestamp(request.get("timestamp", time.time())).strftime("%Y-%m-%d")
                model_usage[model][date_key] += 1
        
        model_forecasts = {}
        for model, daily_model_usage in model_usage.items():
            if len(daily_model_usage) >= 3:
                model_values = list(daily_model_usage.values())
                model_trend = self._calculate_trend_direction(model_values)
                model_avg = statistics.mean(model_values)
                
                model_forecasts[model] = {
                    "current_avg_daily": model_avg,
                    "trend": model_trend,
                    "projected_30d_total": int(model_avg * 30 * (1.1 if model_trend == "increasing" else 0.9 if model_trend == "decreasing" else 1.0))
                }
        
        if model_forecasts:
            forecast["model_forecasts"] = model_forecasts
        
        return forecast
    
    def _get_seasonal_multiplier(self, day_of_week: int, daily_values: List[int], dates: List[str]) -> float:
        """Calculate seasonal multiplier based on day of week patterns."""
        try:
            # Group historical data by day of week
            dow_usage = defaultdict(list)
            
            for i, date_str in enumerate(dates):
                if i < len(daily_values):
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    dow = date_obj.weekday()  # 0 = Monday, 6 = Sunday
                    dow_usage[dow].append(daily_values[i])
            
            # Calculate average for each day of week
            dow_averages = {}
            for dow, values in dow_usage.items():
                if values:
                    dow_averages[dow] = statistics.mean(values)
            
            if not dow_averages:
                return 1.0
            
            overall_avg = statistics.mean(dow_averages.values())
            target_dow_avg = dow_averages.get(day_of_week, overall_avg)
            
            return target_dow_avg / overall_avg if overall_avg > 0 else 1.0
        
        except Exception:
            return 1.0  # Default multiplier if calculation fails
    
    async def _analyze_capacity_needs(self, request_data: List[Dict[str, Any]], performance_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze capacity planning requirements."""
        if not request_data:
            return {"error": "No request data for capacity analysis"}
        
        # Current capacity analysis
        current_analysis = {
            "current_load": {
                "total_requests": len(request_data),
                "time_span_hours": (max(r.get("timestamp", 0) for r in request_data) - 
                                   min(r.get("timestamp", 0) for r in request_data)) / 3600 if request_data else 0
            }
        }
        
        if current_analysis["current_load"]["time_span_hours"] > 0:
            current_analysis["current_load"]["requests_per_hour"] = (
                len(request_data) / current_analysis["current_load"]["time_span_hours"]
            )
        
        # Peak load analysis
        hourly_loads = defaultdict(int)
        for request in request_data:
            hour_key = int(request.get("timestamp", time.time()) // 3600)
            hourly_loads[hour_key] += 1
        
        if hourly_loads:
            hourly_values = list(hourly_loads.values())
            current_analysis["peak_analysis"] = {
                "peak_hourly_requests": max(hourly_values),
                "average_hourly_requests": statistics.mean(hourly_values),
                "peak_to_average_ratio": max(hourly_values) / statistics.mean(hourly_values),
                "load_variability": statistics.stdev(hourly_values) if len(hourly_values) > 1 else 0
            }
        
        # Performance-based capacity analysis
        if performance_data:
            response_times = [p.get("response_time_ms", 0) for p in performance_data if p.get("response_time_ms")]
            if response_times:
                p95_latency = np.percentile(response_times, 95)
                current_analysis["performance_indicators"] = {
                    "p95_latency_ms": p95_latency,
                    "latency_sla_compliance": p95_latency < 5000,  # 5 second SLA
                    "performance_degradation_risk": "high" if p95_latency > 8000 else "medium" if p95_latency > 5000 else "low"
                }
        
        # Capacity recommendations
        recommendations = []
        
        if current_analysis.get("peak_analysis", {}).get("peak_to_average_ratio", 0) > 3:
            recommendations.append({
                "type": "scaling",
                "priority": "medium",
                "description": "High peak-to-average ratio detected",
                "recommendation": "Consider implementing auto-scaling to handle traffic spikes"
            })
        
        if current_analysis.get("performance_indicators", {}).get("performance_degradation_risk") == "high":
            recommendations.append({
                "type": "performance",
                "priority": "high",
                "description": "Performance degradation risk detected",
                "recommendation": "Immediate capacity increase recommended to maintain SLA compliance"
            })
        
        # Future capacity projections
        if len(request_data) > 24:  # At least 24 data points
            recent_load = len([r for r in request_data if r.get("timestamp", 0) > time.time() - 7*24*3600])  # Last 7 days
            earlier_load = len(request_data) - recent_load
            
            if earlier_load > 0:
                growth_rate = (recent_load - earlier_load) / earlier_load
                
                current_analysis["capacity_projections"] = {
                    "current_weekly_load": recent_load,
                    "growth_rate": growth_rate,
                    "projected_30d_load": int(recent_load * 4.3 * (1 + growth_rate)),  # 4.3 weeks in 30 days
                    "projected_90d_load": int(recent_load * 13 * (1 + growth_rate * 3)),  # 13 weeks in 90 days
                    "capacity_increase_needed": growth_rate > 0.2  # 20% growth threshold
                }
        
        current_analysis["recommendations"] = recommendations
        
        return current_analysis
    
    async def _calculate_roi_metrics(self, request_data: List[Dict[str, Any]], cost_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate return on investment metrics."""
        # Extract cost information
        total_cost = 0
        
        # From cost data
        for cost_entry in cost_data:
            total_cost += cost_entry.get("cost_usd", 0)
        
        # From request data
        for request in request_data:
            total_cost += request.get("cost_usd", 0)
        
        if total_cost == 0:
            return {"error": "No cost data available for ROI calculation"}
        
        roi_metrics = {
            "cost_analysis": {
                "total_cost_usd": total_cost,
                "total_requests": len(request_data),
                "cost_per_request": total_cost / len(request_data) if request_data else 0
            }
        }
        
        # Value metrics (simplified - in real implementation, would need business value data)
        # For now, we'll use proxy metrics
        
        # Request success rate as a value indicator
        successful_requests = sum(1 for r in request_data if r.get("status_code", 200) < 400)
        success_rate = successful_requests / len(request_data) if request_data else 0
        
        # Quality score as value indicator
        quality_scores = [r.get("quality_score", 0) for r in request_data if r.get("quality_score")]
        avg_quality = statistics.mean(quality_scores) if quality_scores else 0
        
        # User engagement (unique users as proxy)
        unique_users = len(set(r.get("user_id") for r in request_data if r.get("user_id")))
        
        roi_metrics["value_indicators"] = {
            "success_rate": success_rate,
            "average_quality_score": avg_quality,
            "unique_users_served": unique_users,
            "requests_per_user": len(request_data) / unique_users if unique_users > 0 else 0
        }
        
        # Efficiency metrics
        if request_data:
            # Token efficiency
            total_input_tokens = sum(r.get("tokens_input", 0) for r in request_data)
            total_output_tokens = sum(r.get("tokens_output", 0) for r in request_data)
            
            roi_metrics["efficiency_metrics"] = {
                "total_tokens_processed": total_input_tokens + total_output_tokens,
                "cost_per_token": total_cost / (total_input_tokens + total_output_tokens) if (total_input_tokens + total_output_tokens) > 0 else 0,
                "tokens_per_dollar": (total_input_tokens + total_output_tokens) / total_cost if total_cost > 0 else 0
            }
        
        # ROI calculation (simplified)
        # In a real scenario, you'd need actual business value/revenue data
        estimated_value_per_request = 0.10  # Placeholder - $0.10 value per successful request
        estimated_total_value = successful_requests * estimated_value_per_request
        
        if total_cost > 0:
            roi_metrics["roi_calculation"] = {
                "estimated_value_usd": estimated_total_value,
                "total_cost_usd": total_cost,
                "estimated_roi_ratio": estimated_total_value / total_cost,
                "estimated_roi_percentage": ((estimated_total_value - total_cost) / total_cost) * 100,
                "break_even_requests": int(total_cost / estimated_value_per_request) if estimated_value_per_request > 0 else 0,
                "note": "ROI calculation uses estimated value per request - actual business value may vary"
            }
        
        return roi_metrics
    
    async def _calculate_business_kpis(self, request_data: List[Dict[str, Any]], cost_data: List[Dict[str, Any]], performance_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate key business performance indicators."""
        kpis = {}
        
        # Usage KPIs
        if request_data:
            kpis["usage_kpis"] = {
                "total_requests": len(request_data),
                "unique_users": len(set(r.get("user_id") for r in request_data if r.get("user_id"))),
                "unique_tenants": len(set(r.get("tenant_id") for r in request_data if r.get("tenant_id"))),
                "requests_per_user": len(request_data) / len(set(r.get("user_id") for r in request_data if r.get("user_id"))) if any(r.get("user_id") for r in request_data) else 0,
                "active_models": len(set(r.get("model_used") for r in request_data if r.get("model_used"))),
                "active_providers": len(set(r.get("provider_used") for r in request_data if r.get("provider_used")))
            }
        
        # Quality KPIs
        quality_scores = [r.get("quality_score", 0) for r in request_data if r.get("quality_score")]
        if quality_scores:
            kpis["quality_kpis"] = {
                "average_quality_score": statistics.mean(quality_scores),
                "quality_score_p95": np.percentile(quality_scores, 95),
                "high_quality_percentage": (sum(1 for q in quality_scores if q >= 0.8) / len(quality_scores)) * 100,
                "low_quality_percentage": (sum(1 for q in quality_scores if q < 0.6) / len(quality_scores)) * 100
            }
        
        # Performance KPIs
        if performance_data:
            response_times = [p.get("response_time_ms", 0) for p in performance_data if p.get("response_time_ms")]
            if response_times:
                kpis["performance_kpis"] = {
                    "average_response_time_ms": statistics.mean(response_times),
                    "p95_response_time_ms": np.percentile(response_times, 95),
                    "p99_response_time_ms": np.percentile(response_times, 99),
                    "sla_compliance_percentage": (sum(1 for rt in response_times if rt < 5000) / len(response_times)) * 100
                }
        
        # Reliability KPIs
        if request_data:
            error_requests = sum(1 for r in request_data if r.get("status_code", 200) >= 400)
            kpis["reliability_kpis"] = {
                "success_rate_percentage": ((len(request_data) - error_requests) / len(request_data)) * 100,
                "error_rate_percentage": (error_requests / len(request_data)) * 100,
                "availability_percentage": 99.9  # Placeholder - would need uptime data
            }
        
        # Cost KPIs
        total_cost = sum(c.get("cost_usd", 0) for c in cost_data) + sum(r.get("cost_usd", 0) for r in request_data)
        if total_cost > 0:
            kpis["cost_kpis"] = {
                "total_cost_usd": total_cost,
                "cost_per_request": total_cost / len(request_data) if request_data else 0,
                "cost_per_user": total_cost / len(set(r.get("user_id") for r in request_data if r.get("user_id"))) if any(r.get("user_id") for r in request_data) else 0,
                "daily_burn_rate": total_cost / 30  # Assuming 30-day period
            }
        
        return kpis
    
    def _calculate_trend_direction(self, values: List[float]) -> str:
        """Calculate trend direction from a series of values."""
        if len(values) < 2:
            return "insufficient_data"
        
        # Simple linear trend
        x = list(range(len(values)))
        n = len(values)
        
        sum_x = sum(x)
        sum_y = sum(values)
        sum_xy = sum(x[i] * values[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))
        
        if n * sum_x2 - sum_x ** 2 == 0:
            return "stable"
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
        
        if abs(slope) < 0.01:
            return "stable"
        elif slope > 0:
            return "increasing"
        else:
            return "decreasing"
    
    def _create_time_windows_from_costs(self, cost_data: List[Dict[str, Any]], window_hours: int = 24) -> List[List[Dict[str, Any]]]:
        """Create time windows from cost data."""
        if not cost_data:
            return []
        
        windows = []
        current_window = []
        window_start = cost_data[0]["timestamp"]
        window_size_seconds = window_hours * 3600
        
        for cost_entry in cost_data:
            timestamp = cost_entry["timestamp"]
            
            if timestamp - window_start <= window_size_seconds:
                current_window.append(cost_entry)
            else:
                if current_window:
                    windows.append(current_window)
                current_window = [cost_entry]
                window_start = timestamp
        
        if current_window:
            windows.append(current_window)
        
        return windows    
  
  async def _generate_strategic_recommendations(self, insights: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate strategic business recommendations based on insights."""
        recommendations = []
        
        # Cost optimization recommendations
        cost_analysis = insights.get("cost_analysis", {})
        if cost_analysis:
            daily_trends = cost_analysis.get("daily_trends", {})
            if daily_trends and daily_trends.get("daily_cost_trend") == "increasing":
                recommendations.append({
                    "category": "cost_optimization",
                    "priority": "high",
                    "title": "Rising Cost Trend Detected",
                    "description": "Daily costs are trending upward, requiring immediate attention",
                    "strategic_actions": [
                        "Implement cost monitoring and alerting systems",
                        "Review and optimize model selection strategy",
                        "Consider negotiating volume discounts with providers",
                        "Implement cost budgets and controls for high-spending tenants"
                    ],
                    "expected_impact": "15-25% cost reduction",
                    "timeline": "30-60 days"
                })
            
            cost_by_model = cost_analysis.get("cost_by_model", {})
            if cost_by_model:
                total_costs = cost_by_model.get("total_costs", {})
                if total_costs:
                    # Find models with disproportionate costs
                    sorted_models = sorted(total_costs.items(), key=lambda x: x[1], reverse=True)
                    if len(sorted_models) > 1 and sorted_models[0][1] > sorted_models[1][1] * 3:
                        recommendations.append({
                            "category": "model_optimization",
                            "priority": "medium",
                            "title": "Cost Concentration Risk",
                            "description": f"Model '{sorted_models[0][0]}' accounts for disproportionate costs",
                            "strategic_actions": [
                                "Evaluate alternative models with similar capabilities",
                                "Implement A/B testing for model alternatives",
                                "Consider hybrid routing strategies",
                                "Negotiate better pricing for high-volume models"
                            ],
                            "expected_impact": "10-20% cost reduction",
                            "timeline": "60-90 days"
                        })
        
        # Usage growth recommendations
        usage_forecast = insights.get("usage_forecast", {})
        if usage_forecast:
            forecast_data = usage_forecast.get("forecast", {})
            if forecast_data:
                growth_rate = forecast_data.get("growth_rate_weekly", 0)
                if growth_rate > 0.2:  # 20% weekly growth
                    recommendations.append({
                        "category": "scaling_strategy",
                        "priority": "high",
                        "title": "Rapid Growth Trajectory",
                        "description": f"Usage growing at {growth_rate*100:.1f}% per week",
                        "strategic_actions": [
                            "Prepare infrastructure scaling plans",
                            "Negotiate enterprise pricing tiers",
                            "Implement usage-based pricing models",
                            "Plan for operational team expansion"
                        ],
                        "expected_impact": "Sustainable growth management",
                        "timeline": "Immediate - 90 days"
                    })
        
        # Capacity planning recommendations
        capacity_planning = insights.get("capacity_planning", {})
        if capacity_planning:
            performance_indicators = capacity_planning.get("performance_indicators", {})
            if performance_indicators.get("performance_degradation_risk") == "high":
                recommendations.append({
                    "category": "infrastructure",
                    "priority": "critical",
                    "title": "Performance Degradation Risk",
                    "description": "System performance approaching critical thresholds",
                    "strategic_actions": [
                        "Immediate capacity increase",
                        "Implement load balancing improvements",
                        "Review and optimize system architecture",
                        "Establish performance monitoring and alerting"
                    ],
                    "expected_impact": "Maintain SLA compliance",
                    "timeline": "Immediate - 14 days"
                })
        
        # ROI optimization recommendations
        roi_analysis = insights.get("roi_analysis", {})
        if roi_analysis:
            roi_calc = roi_analysis.get("roi_calculation", {})
            if roi_calc and roi_calc.get("estimated_roi_percentage", 0) < 50:  # Less than 50% ROI
                recommendations.append({
                    "category": "business_optimization",
                    "priority": "medium",
                    "title": "ROI Improvement Opportunity",
                    "description": "Current ROI below optimal thresholds",
                    "strategic_actions": [
                        "Implement value-based pricing strategies",
                        "Focus on high-value use cases and customers",
                        "Optimize operational efficiency",
                        "Develop premium service tiers"
                    ],
                    "expected_impact": "25-50% ROI improvement",
                    "timeline": "90-180 days"
                })
        
        # Business KPI recommendations
        business_kpis = insights.get("business_kpis", {})
        if business_kpis:
            quality_kpis = business_kpis.get("quality_kpis", {})
            if quality_kpis and quality_kpis.get("low_quality_percentage", 0) > 20:
                recommendations.append({
                    "category": "quality_improvement",
                    "priority": "medium",
                    "title": "Quality Enhancement Needed",
                    "description": f"{quality_kpis.get('low_quality_percentage', 0):.1f}% of requests have low quality",
                    "strategic_actions": [
                        "Implement quality-aware routing",
                        "Develop prompt optimization programs",
                        "Establish quality feedback loops",
                        "Invest in model fine-tuning capabilities"
                    ],
                    "expected_impact": "Improved customer satisfaction and retention",
                    "timeline": "60-120 days"
                })
            
            reliability_kpis = business_kpis.get("reliability_kpis", {})
            if reliability_kpis and reliability_kpis.get("error_rate_percentage", 0) > 5:
                recommendations.append({
                    "category": "reliability_improvement",
                    "priority": "high",
                    "title": "Reliability Enhancement Required",
                    "description": f"Error rate at {reliability_kpis.get('error_rate_percentage', 0):.1f}%",
                    "strategic_actions": [
                        "Implement comprehensive error handling",
                        "Establish provider redundancy",
                        "Develop circuit breaker patterns",
                        "Create automated recovery procedures"
                    ],
                    "expected_impact": "Improved system reliability and customer trust",
                    "timeline": "30-60 days"
                })
        
        return recommendations
    
    async def _analyze_market_trends(self, request_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze market trends and competitive positioning."""
        if not request_data:
            return {"error": "No request data for market analysis"}
        
        market_analysis = {}
        
        # Model adoption trends
        model_usage_over_time = defaultdict(lambda: defaultdict(int))
        for request in request_data:
            model = request.get("model_used")
            if model:
                date_key = datetime.fromtimestamp(request.get("timestamp", time.time())).strftime("%Y-%m-%d")
                model_usage_over_time[model][date_key] += 1
        
        model_trends = {}
        for model, daily_usage in model_usage_over_time.items():
            if len(daily_usage) >= 3:
                usage_values = list(daily_usage.values())
                trend = self._calculate_trend_direction(usage_values)
                total_usage = sum(usage_values)
                
                model_trends[model] = {
                    "total_usage": total_usage,
                    "trend": trend,
                    "market_share": total_usage / len(request_data) * 100,
                    "daily_average": statistics.mean(usage_values)
                }
        
        if model_trends:
            # Identify growing and declining models
            growing_models = {k: v for k, v in model_trends.items() if v["trend"] == "increasing"}
            declining_models = {k: v for k, v in model_trends.items() if v["trend"] == "decreasing"}
            
            market_analysis["model_trends"] = {
                "all_models": model_trends,
                "growing_models": growing_models,
                "declining_models": declining_models,
                "market_leaders": dict(sorted(model_trends.items(), key=lambda x: x[1]["market_share"], reverse=True)[:5])
            }
        
        # Provider market analysis
        provider_usage = defaultdict(int)
        provider_performance = defaultdict(list)
        
        for request in request_data:
            provider = request.get("provider_used")
            if provider:
                provider_usage[provider] += 1
                if request.get("response_time_ms"):
                    provider_performance[provider].append(request["response_time_ms"])
        
        if provider_usage:
            total_requests = sum(provider_usage.values())
            provider_analysis = {}
            
            for provider, usage in provider_usage.items():
                market_share = (usage / total_requests) * 100
                avg_performance = statistics.mean(provider_performance[provider]) if provider_performance[provider] else 0
                
                provider_analysis[provider] = {
                    "market_share": market_share,
                    "total_requests": usage,
                    "average_response_time_ms": avg_performance,
                    "performance_rank": 0  # Will be calculated below
                }
            
            # Rank providers by performance
            sorted_by_performance = sorted(provider_analysis.items(), key=lambda x: x[1]["average_response_time_ms"])
            for rank, (provider, data) in enumerate(sorted_by_performance, 1):
                provider_analysis[provider]["performance_rank"] = rank
            
            market_analysis["provider_analysis"] = {
                "market_shares": provider_analysis,
                "market_leader": max(provider_usage.items(), key=lambda x: x[1])[0],
                "performance_leader": sorted_by_performance[0][0] if sorted_by_performance else None
            }
        
        # Usage pattern analysis
        hourly_usage = defaultdict(int)
        for request in request_data:
            hour = datetime.fromtimestamp(request.get("timestamp", time.time())).hour
            hourly_usage[hour] += 1
        
        if hourly_usage:
            peak_hours = sorted(hourly_usage.items(), key=lambda x: x[1], reverse=True)[:3]
            low_hours = sorted(hourly_usage.items(), key=lambda x: x[1])[:3]
            
            market_analysis["usage_patterns"] = {
                "hourly_distribution": dict(hourly_usage),
                "peak_hours": [{"hour": h, "requests": r} for h, r in peak_hours],
                "low_usage_hours": [{"hour": h, "requests": r} for h, r in low_hours],
                "usage_concentration": max(hourly_usage.values()) / statistics.mean(hourly_usage.values()) if hourly_usage else 0
            }
        
        return market_analysis
    
    async def _analyze_user_behavior_patterns(self, request_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze user behavior patterns and segmentation."""
        if not request_data:
            return {"error": "No request data for user behavior analysis"}
        
        behavior_analysis = {}
        
        # User segmentation
        user_metrics = defaultdict(lambda: {
            "total_requests": 0,
            "total_cost": 0,
            "models_used": set(),
            "avg_response_time": [],
            "quality_scores": [],
            "error_count": 0,
            "first_request": None,
            "last_request": None
        })
        
        for request in request_data:
            user_id = request.get("user_id")
            if user_id:
                metrics = user_metrics[user_id]
                metrics["total_requests"] += 1
                metrics["total_cost"] += request.get("cost_usd", 0)
                
                if request.get("model_used"):
                    metrics["models_used"].add(request["model_used"])
                
                if request.get("response_time_ms"):
                    metrics["avg_response_time"].append(request["response_time_ms"])
                
                if request.get("quality_score"):
                    metrics["quality_scores"].append(request["quality_score"])
                
                if request.get("status_code", 200) >= 400:
                    metrics["error_count"] += 1
                
                timestamp = request.get("timestamp", time.time())
                if metrics["first_request"] is None or timestamp < metrics["first_request"]:
                    metrics["first_request"] = timestamp
                if metrics["last_request"] is None or timestamp > metrics["last_request"]:
                    metrics["last_request"] = timestamp
        
        # Process user metrics
        user_segments = {
            "power_users": [],
            "regular_users": [],
            "occasional_users": [],
            "new_users": []
        }
        
        for user_id, metrics in user_metrics.items():
            # Calculate derived metrics
            avg_response_time = statistics.mean(metrics["avg_response_time"]) if metrics["avg_response_time"] else 0
            avg_quality = statistics.mean(metrics["quality_scores"]) if metrics["quality_scores"] else 0
            error_rate = metrics["error_count"] / metrics["total_requests"] if metrics["total_requests"] > 0 else 0
            
            user_profile = {
                "user_id": user_id,
                "total_requests": metrics["total_requests"],
                "total_cost": metrics["total_cost"],
                "models_used_count": len(metrics["models_used"]),
                "avg_response_time_ms": avg_response_time,
                "avg_quality_score": avg_quality,
                "error_rate": error_rate,
                "cost_per_request": metrics["total_cost"] / metrics["total_requests"] if metrics["total_requests"] > 0 else 0,
                "usage_span_days": (metrics["last_request"] - metrics["first_request"]) / (24 * 3600) if metrics["first_request"] and metrics["last_request"] else 0
            }
            
            # Segment users
            if metrics["total_requests"] > 100:
                user_segments["power_users"].append(user_profile)
            elif metrics["total_requests"] > 10:
                user_segments["regular_users"].append(user_profile)
            elif user_profile["usage_span_days"] < 7:
                user_segments["new_users"].append(user_profile)
            else:
                user_segments["occasional_users"].append(user_profile)
        
        behavior_analysis["user_segmentation"] = {
            "total_users": len(user_metrics),
            "power_users": len(user_segments["power_users"]),
            "regular_users": len(user_segments["regular_users"]),
            "occasional_users": len(user_segments["occasional_users"]),
            "new_users": len(user_segments["new_users"])
        }
        
        # Top users analysis
        all_users = []
        for segment_users in user_segments.values():
            all_users.extend(segment_users)
        
        behavior_analysis["top_users"] = {
            "by_requests": sorted(all_users, key=lambda x: x["total_requests"], reverse=True)[:10],
            "by_cost": sorted(all_users, key=lambda x: x["total_cost"], reverse=True)[:10],
            "by_quality": sorted([u for u in all_users if u["avg_quality_score"] > 0], key=lambda x: x["avg_quality_score"], reverse=True)[:10]
        }
        
        # Usage behavior patterns
        if user_segments["power_users"]:
            power_user_avg_requests = statistics.mean(u["total_requests"] for u in user_segments["power_users"])
            power_user_avg_cost = statistics.mean(u["total_cost"] for u in user_segments["power_users"])
            
            behavior_analysis["power_user_insights"] = {
                "average_requests": power_user_avg_requests,
                "average_cost": power_user_avg_cost,
                "cost_contribution": sum(u["total_cost"] for u in user_segments["power_users"]) / sum(user_metrics[uid]["total_cost"] for uid in user_metrics) * 100,
                "request_contribution": sum(u["total_requests"] for u in user_segments["power_users"]) / len(request_data) * 100
            }
        
        # Churn risk analysis (simplified)
        current_time = time.time()
        inactive_threshold = 7 * 24 * 3600  # 7 days
        
        at_risk_users = []
        for user_id, metrics in user_metrics.items():
            if metrics["last_request"] and (current_time - metrics["last_request"]) > inactive_threshold:
                days_inactive = (current_time - metrics["last_request"]) / (24 * 3600)
                at_risk_users.append({
                    "user_id": user_id,
                    "days_inactive": days_inactive,
                    "total_requests": metrics["total_requests"],
                    "total_cost": metrics["total_cost"]
                })
        
        if at_risk_users:
            behavior_analysis["churn_risk"] = {
                "at_risk_users": len(at_risk_users),
                "at_risk_percentage": (len(at_risk_users) / len(user_metrics)) * 100,
                "potential_lost_revenue": sum(u["total_cost"] for u in at_risk_users),
                "top_at_risk": sorted(at_risk_users, key=lambda x: x["total_cost"], reverse=True)[:5]
            }
        
        return behavior_analysis
    
    def get_cached_insights(self) -> Optional[Dict[str, Any]]:
        """Get cached business intelligence insights."""
        if self._insights_cache and (time.time() - self._last_analysis_time) < 3600:  # 1 hour cache
            return self._insights_cache
        return None
    
    def update_kpi_history(self, kpi_name: str, value: float, timestamp: Optional[float] = None) -> None:
        """Update KPI history for trend tracking."""
        if timestamp is None:
            timestamp = time.time()
        
        self._kpi_history[kpi_name].append({
            "timestamp": timestamp,
            "value": value
        })
        
        # Keep only last 1000 data points per KPI
        if len(self._kpi_history[kpi_name]) > 1000:
            self._kpi_history[kpi_name] = self._kpi_history[kpi_name][-1000:]
    
    def get_kpi_trend(self, kpi_name: str, days: int = 30) -> Optional[Dict[str, Any]]:
        """Get KPI trend for specified time period."""
        if kpi_name not in self._kpi_history:
            return None
        
        cutoff_time = time.time() - (days * 24 * 3600)
        recent_data = [
            entry for entry in self._kpi_history[kpi_name]
            if entry["timestamp"] >= cutoff_time
        ]
        
        if len(recent_data) < 2:
            return None
        
        values = [entry["value"] for entry in recent_data]
        
        return {
            "kpi_name": kpi_name,
            "data_points": len(recent_data),
            "current_value": values[-1],
            "trend_direction": self._calculate_trend_direction(values),
            "average_value": statistics.mean(values),
            "min_value": min(values),
            "max_value": max(values),
            "change_percentage": ((values[-1] - values[0]) / values[0] * 100) if values[0] != 0 else 0
        }