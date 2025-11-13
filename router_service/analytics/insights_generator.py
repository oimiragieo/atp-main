"""Insights generation and actionable recommendations for enterprise AI platform."""

import asyncio
import logging
import statistics
import time
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class InsightsGenerator:
    """Generates actionable insights and recommendations from analytics data."""
    
    def __init__(self, config):
        self.config = config
        
        # Insights state
        self._insights_cache = {}
        self._last_generation_time = 0
        self._insight_history = []
        
        # Configuration
        self._confidence_threshold = config.insights_confidence_threshold
        self._update_interval_hours = config.insights_update_interval_hours
        
        # Insight categories and priorities
        self._insight_categories = {
            "performance": {"priority_weight": 1.0, "urgency_multiplier": 1.2},
            "cost": {"priority_weight": 0.8, "urgency_multiplier": 1.0},
            "quality": {"priority_weight": 0.9, "urgency_multiplier": 1.1},
            "reliability": {"priority_weight": 1.0, "urgency_multiplier": 1.3},
            "usage": {"priority_weight": 0.7, "urgency_multiplier": 0.9},
            "security": {"priority_weight": 1.0, "urgency_multiplier": 1.4},
            "optimization": {"priority_weight": 0.6, "urgency_multiplier": 0.8}
        }
        
        logger.info("Insights generator initialized")
    
    async def generate_comprehensive_insights(
        self,
        analytics_data: Dict[str, Any],
        performance_data: Dict[str, Any],
        business_data: Dict[str, Any],
        anomaly_data: Dict[str, Any],
        trend_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate comprehensive insights from all analytics sources."""
        try:
            insights_result = {
                "generation_timestamp": time.time(),
                "confidence_threshold": self._confidence_threshold,
                "insights": [],
                "summary": {},
                "recommendations": [],
                "action_items": []
            }
            
            # Generate insights from each data source
            performance_insights = await self._generate_performance_insights(performance_data)
            cost_insights = await self._generate_cost_insights(analytics_data, business_data)
            quality_insights = await self._generate_quality_insights(analytics_data)
            reliability_insights = await self._generate_reliability_insights(performance_data, anomaly_data)
            usage_insights = await self._generate_usage_insights(analytics_data, business_data)
            trend_insights = await self._generate_trend_insights(trend_data)
            anomaly_insights = await self._generate_anomaly_insights(anomaly_data)
            
            # Combine all insights
            all_insights = []
            all_insights.extend(performance_insights)
            all_insights.extend(cost_insights)
            all_insights.extend(quality_insights)
            all_insights.extend(reliability_insights)
            all_insights.extend(usage_insights)
            all_insights.extend(trend_insights)
            all_insights.extend(anomaly_insights)
            
            # Filter by confidence threshold
            high_confidence_insights = [
                insight for insight in all_insights
                if insight.get("confidence", 0) >= self._confidence_threshold
            ]
            
            # Prioritize insights
            prioritized_insights = self._prioritize_insights(high_confidence_insights)
            insights_result["insights"] = prioritized_insights[:20]  # Top 20 insights
            
            # Generate summary
            insights_result["summary"] = self._generate_insights_summary(prioritized_insights)
            
            # Generate actionable recommendations
            insights_result["recommendations"] = await self._generate_actionable_recommendations(prioritized_insights)
            
            # Generate action items
            insights_result["action_items"] = self._generate_action_items(prioritized_insights)
            
            # Cache results
            self._insights_cache = insights_result
            self._last_generation_time = time.time()
            
            # Store in history
            self._insight_history.append({
                "timestamp": time.time(),
                "insights_count": len(prioritized_insights),
                "high_priority_count": len([i for i in prioritized_insights if i.get("priority", 0) > 0.8]),
                "categories": list(set(i.get("category") for i in prioritized_insights))
            })
            
            # Keep only last 100 history entries
            if len(self._insight_history) > 100:
                self._insight_history = self._insight_history[-100:]
            
            return insights_result
        
        except Exception as e:
            logger.error(f"Error generating comprehensive insights: {e}")
            return {"error": str(e)}
    
    async def _generate_performance_insights(self, performance_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate performance-related insights."""
        insights = []
        
        if not performance_data:
            return insights
        
        # Latency insights
        latency_analysis = performance_data.get("latency_analysis", {})
        if latency_analysis:
            stats = latency_analysis.get("statistics", {})
            p95_latency = stats.get("p95_ms", 0)
            
            if p95_latency > 5000:  # > 5 seconds
                severity = min(1.0, p95_latency / 10000)  # Scale to 0-1
                insights.append({
                    "id": f"perf_latency_{int(time.time())}",
                    "category": "performance",
                    "type": "latency_issue",
                    "title": "High Response Latency Detected",
                    "description": f"P95 response time is {p95_latency:.0f}ms, significantly above optimal thresholds",
                    "severity": severity,
                    "confidence": 0.9,
                    "priority": severity * self._insight_categories["performance"]["priority_weight"],
                    "metrics": {
                        "current_p95_ms": p95_latency,
                        "threshold_ms": 5000,
                        "deviation_factor": p95_latency / 5000
                    },
                    "impact": "User experience degradation, potential SLA violations",
                    "root_causes": [
                        "Infrastructure capacity constraints",
                        "Model processing complexity",
                        "Network latency issues",
                        "Provider performance degradation"
                    ],
                    "recommendations": [
                        "Implement request caching for frequently accessed content",
                        "Consider model optimization or alternative models",
                        "Scale infrastructure resources",
                        "Implement request timeout and retry logic"
                    ]
                })
            
            # Model-specific latency insights
            by_model = latency_analysis.get("by_model", {})
            if by_model:
                slow_models = {
                    model: data for model, data in by_model.items()
                    if data.get("p95_ms", 0) > 8000
                }
                
                if slow_models:
                    insights.append({
                        "id": f"perf_slow_models_{int(time.time())}",
                        "category": "performance",
                        "type": "model_performance",
                        "title": "Slow Models Identified",
                        "description": f"Models with poor latency performance: {', '.join(slow_models.keys())}",
                        "severity": 0.7,
                        "confidence": 0.85,
                        "priority": 0.7 * self._insight_categories["performance"]["priority_weight"],
                        "metrics": {
                            "slow_models": slow_models,
                            "threshold_ms": 8000
                        },
                        "impact": "Degraded performance for specific model requests",
                        "recommendations": [
                            "Evaluate alternative models with better performance",
                            "Implement model-specific routing and timeouts",
                            "Consider model optimization or fine-tuning"
                        ]
                    })
        
        # Throughput insights
        throughput_analysis = performance_data.get("throughput_analysis", {})
        if throughput_analysis:
            peak_analysis = throughput_analysis.get("peak_analysis", {})
            if peak_analysis:
                peak_ratio = peak_analysis.get("peak_to_average_ratio", 0)
                
                if peak_ratio > 5:  # High variability
                    insights.append({
                        "id": f"perf_throughput_variability_{int(time.time())}",
                        "category": "performance",
                        "type": "throughput_variability",
                        "title": "High Throughput Variability",
                        "description": f"Peak traffic is {peak_ratio:.1f}x average, indicating high variability",
                        "severity": 0.6,
                        "confidence": 0.8,
                        "priority": 0.6 * self._insight_categories["performance"]["priority_weight"],
                        "metrics": {
                            "peak_to_average_ratio": peak_ratio,
                            "threshold_ratio": 5.0
                        },
                        "impact": "Potential capacity planning challenges and resource inefficiency",
                        "recommendations": [
                            "Implement auto-scaling based on demand patterns",
                            "Analyze traffic patterns for predictive scaling",
                            "Consider load balancing improvements"
                        ]
                    })
        
        return insights
    
    async def _generate_cost_insights(self, analytics_data: Dict[str, Any], business_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate cost-related insights."""
        insights = []
        
        # Cost trend insights from business data
        if business_data:
            cost_analysis = business_data.get("cost_analysis", {})
            if cost_analysis:
                daily_trends = cost_analysis.get("daily_trends", {})
                if daily_trends and daily_trends.get("daily_cost_trend") == "increasing":
                    avg_daily_cost = daily_trends.get("average_daily_cost", 0)
                    
                    insights.append({
                        "id": f"cost_trend_increase_{int(time.time())}",
                        "category": "cost",
                        "type": "cost_trend",
                        "title": "Rising Cost Trend",
                        "description": f"Daily costs are trending upward with average of ${avg_daily_cost:.2f}/day",
                        "severity": 0.7,
                        "confidence": 0.85,
                        "priority": 0.7 * self._insight_categories["cost"]["priority_weight"],
                        "metrics": {
                            "average_daily_cost": avg_daily_cost,
                            "trend_direction": "increasing"
                        },
                        "impact": "Increasing operational expenses and budget pressure",
                        "recommendations": [
                            "Implement cost monitoring and alerting",
                            "Review model selection for cost efficiency",
                            "Consider usage optimization strategies",
                            "Negotiate volume discounts with providers"
                        ]
                    })
                
                # Model cost concentration
                cost_by_model = cost_analysis.get("cost_by_model", {})
                if cost_by_model:
                    total_costs = cost_by_model.get("total_costs", {})
                    if total_costs:
                        sorted_models = sorted(total_costs.items(), key=lambda x: x[1], reverse=True)
                        if len(sorted_models) > 1:
                            top_model_cost = sorted_models[0][1]
                            total_cost = sum(total_costs.values())
                            concentration = (top_model_cost / total_cost) * 100
                            
                            if concentration > 60:  # High concentration
                                insights.append({
                                    "id": f"cost_concentration_{int(time.time())}",
                                    "category": "cost",
                                    "type": "cost_concentration",
                                    "title": "High Cost Concentration Risk",
                                    "description": f"Model '{sorted_models[0][0]}' accounts for {concentration:.1f}% of total costs",
                                    "severity": 0.6,
                                    "confidence": 0.9,
                                    "priority": 0.6 * self._insight_categories["cost"]["priority_weight"],
                                    "metrics": {
                                        "top_model": sorted_models[0][0],
                                        "concentration_percentage": concentration,
                                        "top_model_cost": top_model_cost
                                    },
                                    "impact": "High dependency on single model creates cost risk",
                                    "recommendations": [
                                        "Diversify model usage to reduce concentration risk",
                                        "Evaluate alternative models for cost efficiency",
                                        "Implement cost-aware routing strategies"
                                    ]
                                })
        
        # Request-level cost insights
        if analytics_data:
            patterns = analytics_data.get("patterns", {})
            if patterns:
                request_size_dist = patterns.get("request_size_distribution", {})
                if request_size_dist:
                    large_requests = request_size_dist.get("large_requests", 0)
                    total_requests = (request_size_dist.get("small_requests", 0) + 
                                    request_size_dist.get("medium_requests", 0) + 
                                    large_requests)
                    
                    if total_requests > 0:
                        large_request_percentage = (large_requests / total_requests) * 100
                        
                        if large_request_percentage > 20:  # High percentage of large requests
                            insights.append({
                                "id": f"cost_large_requests_{int(time.time())}",
                                "category": "cost",
                                "type": "request_size_cost",
                                "title": "High Proportion of Large Requests",
                                "description": f"{large_request_percentage:.1f}% of requests are large (>5K tokens)",
                                "severity": 0.5,
                                "confidence": 0.8,
                                "priority": 0.5 * self._insight_categories["cost"]["priority_weight"],
                                "metrics": {
                                    "large_request_percentage": large_request_percentage,
                                    "large_requests_count": large_requests,
                                    "total_requests": total_requests
                                },
                                "impact": "Large requests drive higher costs per interaction",
                                "recommendations": [
                                    "Implement request size limits and validation",
                                    "Optimize prompts to reduce token usage",
                                    "Consider chunking large requests",
                                    "Implement cost-aware request handling"
                                ]
                            })
        
        return insights
    
    async def _generate_quality_insights(self, analytics_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate quality-related insights."""
        insights = []
        
        if not analytics_data:
            return insights
        
        # Model quality insights
        model_patterns = analytics_data.get("model_patterns", {})
        if model_patterns:
            model_performance = model_patterns.get("model_performance", {})
            
            # Find models with low quality scores
            low_quality_models = {}
            for model, perf in model_performance.items():
                avg_quality = perf.get("avg_quality_score", 0)
                if avg_quality > 0 and avg_quality < 0.7:  # Below 70% quality
                    low_quality_models[model] = {
                        "quality_score": avg_quality,
                        "request_count": perf.get("total_requests", 0)
                    }
            
            if low_quality_models:
                total_low_quality_requests = sum(data["request_count"] for data in low_quality_models.values())
                
                insights.append({
                    "id": f"quality_low_models_{int(time.time())}",
                    "category": "quality",
                    "type": "model_quality",
                    "title": "Low Quality Models Detected",
                    "description": f"{len(low_quality_models)} models have quality scores below 70%",
                    "severity": 0.6,
                    "confidence": 0.85,
                    "priority": 0.6 * self._insight_categories["quality"]["priority_weight"],
                    "metrics": {
                        "low_quality_models": low_quality_models,
                        "affected_requests": total_low_quality_requests,
                        "quality_threshold": 0.7
                    },
                    "impact": "Poor user experience and reduced satisfaction",
                    "recommendations": [
                        "Review and optimize prompts for affected models",
                        "Consider alternative models with better quality",
                        "Implement quality-aware routing",
                        "Establish quality monitoring and feedback loops"
                    ]
                })
            
            # Model efficiency insights
            most_efficient = model_patterns.get("most_efficient_models", {})
            if most_efficient and len(model_performance) > 1:
                # Compare efficiency across models
                efficiency_scores = {}
                for model, perf in model_performance.items():
                    cost = perf.get("avg_cost_per_request", 0)
                    quality = perf.get("avg_quality_score", 0)
                    if cost > 0 and quality > 0:
                        efficiency_scores[model] = quality / cost
                
                if len(efficiency_scores) > 1:
                    sorted_efficiency = sorted(efficiency_scores.items(), key=lambda x: x[1], reverse=True)
                    best_efficiency = sorted_efficiency[0][1]
                    worst_efficiency = sorted_efficiency[-1][1]
                    
                    if best_efficiency > worst_efficiency * 2:  # Significant efficiency gap
                        insights.append({
                            "id": f"quality_efficiency_gap_{int(time.time())}",
                            "category": "quality",
                            "type": "efficiency_optimization",
                            "title": "Model Efficiency Optimization Opportunity",
                            "description": f"Significant efficiency gap between models (best: {sorted_efficiency[0][0]})",
                            "severity": 0.4,
                            "confidence": 0.8,
                            "priority": 0.4 * self._insight_categories["quality"]["priority_weight"],
                            "metrics": {
                                "most_efficient_model": sorted_efficiency[0][0],
                                "least_efficient_model": sorted_efficiency[-1][0],
                                "efficiency_ratio": best_efficiency / worst_efficiency
                            },
                            "impact": "Suboptimal cost-quality balance across models",
                            "recommendations": [
                                "Prioritize high-efficiency models for similar use cases",
                                "Implement efficiency-based routing",
                                "Review pricing and quality trade-offs"
                            ]
                        })
        
        return insights
    
    async def _generate_reliability_insights(self, performance_data: Dict[str, Any], anomaly_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate reliability-related insights."""
        insights = []
        
        # Error rate insights
        if performance_data:
            error_analysis = performance_data.get("error_analysis", {})
            if error_analysis:
                error_rate = error_analysis.get("error_rate_percent", 0)
                
                if error_rate > 5:  # > 5% error rate
                    severity = min(1.0, error_rate / 20)  # Scale to 0-1
                    insights.append({
                        "id": f"reliability_error_rate_{int(time.time())}",
                        "category": "reliability",
                        "type": "error_rate",
                        "title": "High Error Rate Detected",
                        "description": f"Current error rate is {error_rate:.1f}%, above acceptable thresholds",
                        "severity": severity,
                        "confidence": 0.95,
                        "priority": severity * self._insight_categories["reliability"]["priority_weight"],
                        "metrics": {
                            "current_error_rate": error_rate,
                            "threshold": 5.0,
                            "total_errors": error_analysis.get("error_requests", 0)
                        },
                        "impact": "Reduced system reliability and user trust",
                        "recommendations": [
                            "Implement comprehensive error handling and retry logic",
                            "Investigate root causes of errors",
                            "Establish provider health monitoring",
                            "Implement circuit breaker patterns"
                        ]
                    })
                
                # Provider-specific reliability issues
                by_provider = error_analysis.get("by_provider", {})
                problematic_providers = {
                    provider: data for provider, data in by_provider.items()
                    if data.get("error_rate_percent", 0) > 10
                }
                
                if problematic_providers:
                    insights.append({
                        "id": f"reliability_provider_issues_{int(time.time())}",
                        "category": "reliability",
                        "type": "provider_reliability",
                        "title": "Provider Reliability Issues",
                        "description": f"Providers with high error rates: {', '.join(problematic_providers.keys())}",
                        "severity": 0.7,
                        "confidence": 0.9,
                        "priority": 0.7 * self._insight_categories["reliability"]["priority_weight"],
                        "metrics": {
                            "problematic_providers": problematic_providers,
                            "error_threshold": 10.0
                        },
                        "impact": "Provider-specific reliability concerns affecting service quality",
                        "recommendations": [
                            "Reduce traffic to problematic providers",
                            "Implement provider health checks and failover",
                            "Contact providers about reliability issues",
                            "Consider alternative providers"
                        ]
                    })
        
        # Anomaly-based reliability insights
        if anomaly_data:
            anomalies = anomaly_data.get("anomalies_detected", [])
            high_severity_anomalies = [a for a in anomalies if a.get("severity_score", 0) > 0.8]
            
            if high_severity_anomalies:
                insights.append({
                    "id": f"reliability_anomalies_{int(time.time())}",
                    "category": "reliability",
                    "type": "anomaly_detection",
                    "title": "High-Severity Anomalies Detected",
                    "description": f"{len(high_severity_anomalies)} high-severity anomalies detected",
                    "severity": 0.8,
                    "confidence": 0.85,
                    "priority": 0.8 * self._insight_categories["reliability"]["priority_weight"],
                    "metrics": {
                        "high_severity_count": len(high_severity_anomalies),
                        "total_anomalies": len(anomalies),
                        "anomaly_types": list(set(a.get("anomaly_type") for a in high_severity_anomalies))
                    },
                    "impact": "Potential system instability and service disruption",
                    "recommendations": [
                        "Investigate high-severity anomalies immediately",
                        "Implement proactive anomaly monitoring",
                        "Establish anomaly response procedures",
                        "Review system stability and resilience"
                    ]
                })
        
        return insights
    
    async def _generate_usage_insights(self, analytics_data: Dict[str, Any], business_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate usage-related insights."""
        insights = []
        
        # User behavior insights
        if analytics_data:
            user_patterns = analytics_data.get("user_patterns", {})
            if user_patterns:
                user_categories = user_patterns.get("user_categories", {})
                if user_categories:
                    total_users = user_categories.get("total_users", 0)
                    heavy_users = user_categories.get("heavy_users", 0)
                    
                    if total_users > 0:
                        heavy_user_percentage = (heavy_users / total_users) * 100
                        
                        if heavy_user_percentage > 20:  # High percentage of heavy users
                            insights.append({
                                "id": f"usage_heavy_users_{int(time.time())}",
                                "category": "usage",
                                "type": "user_concentration",
                                "title": "High Concentration of Heavy Users",
                                "description": f"{heavy_user_percentage:.1f}% of users are heavy users (>100 requests)",
                                "severity": 0.4,
                                "confidence": 0.8,
                                "priority": 0.4 * self._insight_categories["usage"]["priority_weight"],
                                "metrics": {
                                    "heavy_user_percentage": heavy_user_percentage,
                                    "heavy_users_count": heavy_users,
                                    "total_users": total_users
                                },
                                "impact": "High dependency on small user base creates usage risk",
                                "recommendations": [
                                    "Implement user engagement programs for broader adoption",
                                    "Analyze heavy user patterns for optimization opportunities",
                                    "Consider tiered pricing for different usage levels"
                                ]
                            })
        
        # Business usage insights
        if business_data:
            usage_forecast = business_data.get("usage_forecast", {})
            if usage_forecast:
                forecast_data = usage_forecast.get("forecast", {})
                if forecast_data:
                    growth_rate = forecast_data.get("growth_rate_weekly", 0)
                    
                    if growth_rate > 0.3:  # >30% weekly growth
                        insights.append({
                            "id": f"usage_rapid_growth_{int(time.time())}",
                            "category": "usage",
                            "type": "growth_trend",
                            "title": "Rapid Usage Growth Detected",
                            "description": f"Usage growing at {growth_rate*100:.1f}% per week",
                            "severity": 0.6,
                            "confidence": 0.8,
                            "priority": 0.6 * self._insight_categories["usage"]["priority_weight"],
                            "metrics": {
                                "weekly_growth_rate": growth_rate,
                                "growth_threshold": 0.3
                            },
                            "impact": "Rapid growth may strain system capacity and resources",
                            "recommendations": [
                                "Prepare capacity scaling plans",
                                "Monitor system performance during growth",
                                "Plan for operational team expansion",
                                "Implement usage monitoring and alerting"
                            ]
                        })
        
        return insights
    
    async def _generate_trend_insights(self, trend_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate trend-based insights."""
        insights = []
        
        if not trend_data:
            return insights
        
        trend_insights = trend_data.get("insights", [])
        for trend_insight in trend_insights:
            # Convert trend insights to our format
            insight_type = trend_insight.get("type", "trend")
            priority_map = {
                "critical": 1.0,
                "high": 0.8,
                "medium": 0.6,
                "low": 0.4
            }
            
            priority_level = trend_insight.get("priority", "medium")
            priority_score = priority_map.get(priority_level, 0.6)
            
            insights.append({
                "id": f"trend_{insight_type}_{int(time.time())}",
                "category": "optimization",
                "type": f"trend_{insight_type}",
                "title": trend_insight.get("title", "Trend Insight"),
                "description": trend_insight.get("description", ""),
                "severity": priority_score,
                "confidence": 0.8,  # Default confidence for trend insights
                "priority": priority_score * self._insight_categories["optimization"]["priority_weight"],
                "metrics": {
                    "metric": trend_insight.get("metric"),
                    "current_value": trend_insight.get("current_value"),
                    "trend_direction": trend_insight.get("trend_direction")
                },
                "impact": "Trend-based optimization opportunity",
                "recommendations": trend_insight.get("recommendations", [])
            })
        
        return insights
    
    async def _generate_anomaly_insights(self, anomaly_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate anomaly-based insights."""
        insights = []
        
        if not anomaly_data:
            return insights
        
        summary = anomaly_data.get("summary", {})
        if summary:
            total_anomalies = summary.get("total_anomalies", 0)
            high_severity = summary.get("high_severity_anomalies", 0)
            
            if high_severity > 0:
                severity_ratio = high_severity / total_anomalies if total_anomalies > 0 else 0
                
                insights.append({
                    "id": f"anomaly_high_severity_{int(time.time())}",
                    "category": "security",
                    "type": "anomaly_pattern",
                    "title": "High-Severity Anomaly Pattern",
                    "description": f"{high_severity} high-severity anomalies detected out of {total_anomalies} total",
                    "severity": min(1.0, severity_ratio * 2),
                    "confidence": 0.85,
                    "priority": min(1.0, severity_ratio * 2) * self._insight_categories["security"]["priority_weight"],
                    "metrics": {
                        "high_severity_count": high_severity,
                        "total_anomalies": total_anomalies,
                        "severity_ratio": severity_ratio
                    },
                    "impact": "Potential security or stability concerns",
                    "recommendations": [
                        "Investigate high-severity anomalies immediately",
                        "Review security and access patterns",
                        "Implement enhanced monitoring",
                        "Consider implementing additional safeguards"
                    ]
                })
        
        return insights
    
    def _prioritize_insights(self, insights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prioritize insights based on severity, confidence, and category."""
        def calculate_priority_score(insight):
            base_priority = insight.get("priority", 0.5)
            confidence = insight.get("confidence", 0.5)
            severity = insight.get("severity", 0.5)
            category = insight.get("category", "optimization")
            
            # Apply category-specific multipliers
            category_config = self._insight_categories.get(category, {"urgency_multiplier": 1.0})
            urgency_multiplier = category_config["urgency_multiplier"]
            
            # Calculate final priority score
            priority_score = (base_priority * 0.4 + confidence * 0.3 + severity * 0.3) * urgency_multiplier
            
            return min(1.0, priority_score)
        
        # Calculate priority scores
        for insight in insights:
            insight["calculated_priority"] = calculate_priority_score(insight)
        
        # Sort by priority score (descending)
        return sorted(insights, key=lambda x: x["calculated_priority"], reverse=True)
    
    def _generate_insights_summary(self, insights: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary of insights."""
        if not insights:
            return {"total_insights": 0}
        
        # Category distribution
        category_counts = Counter(insight.get("category") for insight in insights)
        
        # Severity distribution
        severity_distribution = {
            "critical": len([i for i in insights if i.get("severity", 0) > 0.8]),
            "high": len([i for i in insights if 0.6 < i.get("severity", 0) <= 0.8]),
            "medium": len([i for i in insights if 0.4 < i.get("severity", 0) <= 0.6]),
            "low": len([i for i in insights if i.get("severity", 0) <= 0.4])
        }
        
        # Top categories
        top_categories = dict(category_counts.most_common(5))
        
        # Average confidence
        avg_confidence = statistics.mean(i.get("confidence", 0) for i in insights)
        
        return {
            "total_insights": len(insights),
            "category_distribution": top_categories,
            "severity_distribution": severity_distribution,
            "average_confidence": avg_confidence,
            "high_priority_insights": len([i for i in insights if i.get("calculated_priority", 0) > 0.7]),
            "actionable_insights": len([i for i in insights if i.get("recommendations")])
        }
    
    async def _generate_actionable_recommendations(self, insights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate actionable recommendations from insights."""
        recommendations = []
        
        # Group insights by category for consolidated recommendations
        category_insights = defaultdict(list)
        for insight in insights:
            category = insight.get("category", "general")
            category_insights[category].append(insight)
        
        # Generate category-specific recommendations
        for category, cat_insights in category_insights.items():
            if not cat_insights:
                continue
            
            # Find most critical insight in category
            critical_insight = max(cat_insights, key=lambda x: x.get("calculated_priority", 0))
            
            # Aggregate recommendations
            all_recommendations = []
            for insight in cat_insights:
                all_recommendations.extend(insight.get("recommendations", []))
            
            # Remove duplicates while preserving order
            unique_recommendations = []
            seen = set()
            for rec in all_recommendations:
                if rec not in seen:
                    unique_recommendations.append(rec)
                    seen.add(rec)
            
            if unique_recommendations:
                recommendations.append({
                    "category": category,
                    "priority": critical_insight.get("calculated_priority", 0.5),
                    "title": f"{category.title()} Optimization Recommendations",
                    "description": f"Based on {len(cat_insights)} insights in {category} category",
                    "recommendations": unique_recommendations[:5],  # Top 5 recommendations
                    "affected_insights": len(cat_insights),
                    "estimated_impact": self._estimate_recommendation_impact(category, cat_insights)
                })
        
        return sorted(recommendations, key=lambda x: x["priority"], reverse=True)
    
    def _estimate_recommendation_impact(self, category: str, insights: List[Dict[str, Any]]) -> str:
        """Estimate the impact of implementing recommendations."""
        avg_severity = statistics.mean(i.get("severity", 0) for i in insights)
        
        impact_map = {
            "performance": {
                "high": "20-40% improvement in response times",
                "medium": "10-20% improvement in response times",
                "low": "5-10% improvement in response times"
            },
            "cost": {
                "high": "15-30% reduction in operational costs",
                "medium": "8-15% reduction in operational costs",
                "low": "3-8% reduction in operational costs"
            },
            "reliability": {
                "high": "Significant improvement in system stability",
                "medium": "Moderate improvement in error rates",
                "low": "Minor improvement in reliability metrics"
            },
            "quality": {
                "high": "Major improvement in user satisfaction",
                "medium": "Noticeable improvement in quality scores",
                "low": "Incremental quality improvements"
            }
        }
        
        if avg_severity > 0.7:
            impact_level = "high"
        elif avg_severity > 0.4:
            impact_level = "medium"
        else:
            impact_level = "low"
        
        return impact_map.get(category, {}).get(impact_level, "Positive impact on system performance")
    
    def _generate_action_items(self, insights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate specific action items from insights."""
        action_items = []
        
        # High-priority insights become immediate action items
        high_priority_insights = [i for i in insights if i.get("calculated_priority", 0) > 0.8]
        
        for insight in high_priority_insights:
            recommendations = insight.get("recommendations", [])
            if recommendations:
                action_items.append({
                    "id": f"action_{insight.get('id', 'unknown')}",
                    "title": f"Address {insight.get('title', 'Issue')}",
                    "description": insight.get("description", ""),
                    "priority": "high" if insight.get("calculated_priority", 0) > 0.9 else "medium",
                    "category": insight.get("category", "general"),
                    "urgency": "immediate" if insight.get("severity", 0) > 0.8 else "within_week",
                    "actions": recommendations[:3],  # Top 3 actions
                    "estimated_effort": self._estimate_effort(insight),
                    "expected_outcome": insight.get("impact", "Improved system performance")
                })
        
        return action_items[:10]  # Top 10 action items
    
    def _estimate_effort(self, insight: Dict[str, Any]) -> str:
        """Estimate effort required to address insight."""
        category = insight.get("category", "general")
        severity = insight.get("severity", 0.5)
        
        if category in ["security", "reliability"] and severity > 0.8:
            return "high"
        elif category in ["performance", "cost"] and severity > 0.6:
            return "medium"
        else:
            return "low"
    
    def get_cached_insights(self) -> Optional[Dict[str, Any]]:
        """Get cached insights if still valid."""
        if (self._insights_cache and 
            (time.time() - self._last_generation_time) < (self._update_interval_hours * 3600)):
            return self._insights_cache
        return None
    
    def get_insights_history(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get insights generation history."""
        cutoff_time = time.time() - (days * 24 * 3600)
        
        return [
            entry for entry in self._insight_history
            if entry["timestamp"] >= cutoff_time
        ]
    
    def update_confidence_threshold(self, new_threshold: float) -> None:
        """Update confidence threshold for insights."""
        self._confidence_threshold = max(0.1, min(0.99, new_threshold))
        logger.info(f"Updated insights confidence threshold to {self._confidence_threshold}")