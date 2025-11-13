"""Trend analysis and forecasting for enterprise AI platform."""

import asyncio
import logging
import statistics
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    """Analyzes trends and generates forecasts for various metrics."""
    
    def __init__(self, config):
        self.config = config
        
        # Trend analysis state
        self._trend_history = defaultdict(deque)
        self._forecast_models = {}
        self._seasonal_patterns = {}
        
        # Configuration
        self._trend_window_days = config.trend_window_days
        self._seasonal_analysis = config.seasonal_analysis
        self._forecast_horizon_days = config.forecast_horizon_days
        
        # Trend detection parameters
        self._min_data_points = 10
        self._significance_threshold = 0.05
        
        logger.info("Trend analyzer initialized")
    
    async def analyze_trends(
        self,
        metrics_data: List[Dict[str, Any]],
        metric_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Analyze trends across multiple metrics."""
        if not metrics_data:
            return {"error": "No metrics data provided"}
        
        try:
            # Filter recent data
            cutoff_time = time.time() - (self._trend_window_days * 24 * 3600)
            recent_metrics = [m for m in metrics_data if m.get("timestamp", 0) >= cutoff_time]
            
            if len(recent_metrics) < self._min_data_points:
                return {"error": f"Insufficient data for trend analysis (minimum {self._min_data_points} points required)"}
            
            # Sort by timestamp
            recent_metrics.sort(key=lambda x: x.get("timestamp", 0))
            
            analysis_result = {
                "analysis_timestamp": time.time(),
                "data_points_analyzed": len(recent_metrics),
                "trend_window_days": self._trend_window_days,
                "trends": {}
            }
            
            # Default metric types if not specified
            if metric_types is None:
                metric_types = [
                    "response_time", "error_rate", "cost", "throughput", 
                    "quality_score", "token_usage", "user_activity"
                ]
            
            # Analyze each metric type
            for metric_type in metric_types:
                trend_analysis = await self._analyze_metric_trend(recent_metrics, metric_type)
                if trend_analysis:
                    analysis_result["trends"][metric_type] = trend_analysis
            
            # Overall system health trend
            analysis_result["system_health_trend"] = await self._analyze_system_health_trend(recent_metrics)
            
            # Seasonal patterns (if enabled)
            if self._seasonal_analysis:
                analysis_result["seasonal_patterns"] = await self._analyze_seasonal_patterns(recent_metrics)
            
            # Forecasting
            analysis_result["forecasts"] = await self._generate_forecasts(analysis_result["trends"])
            
            # Trend insights and recommendations
            analysis_result["insights"] = await self._generate_trend_insights(analysis_result)
            
            return analysis_result
        
        except Exception as e:
            logger.error(f"Error analyzing trends: {e}")
            return {"error": str(e)}
    
    async def _analyze_metric_trend(self, metrics_data: List[Dict[str, Any]], metric_type: str) -> Optional[Dict[str, Any]]:
        """Analyze trend for a specific metric type."""
        try:
            # Extract time series data based on metric type
            time_series = await self._extract_time_series(metrics_data, metric_type)
            
            if len(time_series) < self._min_data_points:
                return None
            
            timestamps = [point["timestamp"] for point in time_series]
            values = [point["value"] for point in time_series]
            
            # Basic trend statistics
            trend_stats = {
                "data_points": len(time_series),
                "time_span_days": (max(timestamps) - min(timestamps)) / (24 * 3600),
                "current_value": values[-1],
                "initial_value": values[0],
                "min_value": min(values),
                "max_value": max(values),
                "mean_value": statistics.mean(values),
                "std_dev": statistics.stdev(values) if len(values) > 1 else 0
            }
            
            # Linear trend analysis
            linear_trend = self._calculate_linear_trend(timestamps, values)
            trend_stats.update(linear_trend)
            
            # Trend classification
            trend_stats["trend_classification"] = self._classify_trend(linear_trend)
            
            # Volatility analysis
            trend_stats["volatility"] = self._calculate_volatility(values)
            
            # Change points detection
            change_points = self._detect_change_points(timestamps, values)
            if change_points:
                trend_stats["change_points"] = change_points
            
            # Recent trend (last 25% of data)
            recent_cutoff = int(len(values) * 0.75)
            if recent_cutoff < len(values) - 2:
                recent_values = values[recent_cutoff:]
                recent_timestamps = timestamps[recent_cutoff:]
                recent_trend = self._calculate_linear_trend(recent_timestamps, recent_values)
                trend_stats["recent_trend"] = {
                    "slope": recent_trend["slope"],
                    "direction": recent_trend["direction"],
                    "strength": recent_trend["r_squared"]
                }
            
            # Store in history for future analysis
            self._trend_history[metric_type].extend(time_series)
            if len(self._trend_history[metric_type]) > 1000:  # Keep last 1000 points
                self._trend_history[metric_type] = deque(list(self._trend_history[metric_type])[-1000:])
            
            return trend_stats
        
        except Exception as e:
            logger.error(f"Error analyzing {metric_type} trend: {e}")
            return None
    
    async def _extract_time_series(self, metrics_data: List[Dict[str, Any]], metric_type: str) -> List[Dict[str, Any]]:
        """Extract time series data for a specific metric type."""
        time_series = []
        
        if metric_type == "response_time":
            # Extract response time data
            for metric in metrics_data:
                if metric.get("response_time_ms") is not None:
                    time_series.append({
                        "timestamp": metric.get("timestamp", time.time()),
                        "value": metric["response_time_ms"]
                    })
        
        elif metric_type == "error_rate":
            # Calculate error rate in time windows
            time_windows = self._create_time_windows(metrics_data, window_minutes=30)
            for window in time_windows:
                if window:
                    errors = sum(1 for m in window if m.get("status_code", 200) >= 400)
                    error_rate = (errors / len(window)) * 100
                    time_series.append({
                        "timestamp": window[0].get("timestamp", time.time()),
                        "value": error_rate
                    })
        
        elif metric_type == "cost":
            # Extract cost data
            for metric in metrics_data:
                if metric.get("cost_usd") is not None:
                    time_series.append({
                        "timestamp": metric.get("timestamp", time.time()),
                        "value": metric["cost_usd"]
                    })
        
        elif metric_type == "throughput":
            # Calculate throughput in time windows
            time_windows = self._create_time_windows(metrics_data, window_minutes=60)
            for window in time_windows:
                if window:
                    throughput = len(window)  # Requests per hour
                    time_series.append({
                        "timestamp": window[0].get("timestamp", time.time()),
                        "value": throughput
                    })
        
        elif metric_type == "quality_score":
            # Extract quality scores
            for metric in metrics_data:
                if metric.get("quality_score") is not None:
                    time_series.append({
                        "timestamp": metric.get("timestamp", time.time()),
                        "value": metric["quality_score"]
                    })
        
        elif metric_type == "token_usage":
            # Calculate total token usage in time windows
            time_windows = self._create_time_windows(metrics_data, window_minutes=60)
            for window in time_windows:
                if window:
                    total_tokens = sum(
                        m.get("tokens_input", 0) + m.get("tokens_output", 0) 
                        for m in window
                    )
                    time_series.append({
                        "timestamp": window[0].get("timestamp", time.time()),
                        "value": total_tokens
                    })
        
        elif metric_type == "user_activity":
            # Calculate unique users in time windows
            time_windows = self._create_time_windows(metrics_data, window_minutes=60)
            for window in time_windows:
                if window:
                    unique_users = len(set(m.get("user_id") for m in window if m.get("user_id")))
                    time_series.append({
                        "timestamp": window[0].get("timestamp", time.time()),
                        "value": unique_users
                    })
        
        return sorted(time_series, key=lambda x: x["timestamp"])
    
    def _calculate_linear_trend(self, timestamps: List[float], values: List[float]) -> Dict[str, Any]:
        """Calculate linear trend statistics."""
        if len(timestamps) < 2:
            return {"slope": 0, "intercept": 0, "r_squared": 0, "direction": "stable"}
        
        # Convert timestamps to relative time (hours from start)
        start_time = min(timestamps)
        x = [(t - start_time) / 3600 for t in timestamps]  # Hours
        y = values
        
        # Calculate linear regression
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))
        sum_y2 = sum(y[i] ** 2 for i in range(n))
        
        # Slope and intercept
        denominator = n * sum_x2 - sum_x ** 2
        if denominator == 0:
            slope = 0
            intercept = statistics.mean(y)
        else:
            slope = (n * sum_xy - sum_x * sum_y) / denominator
            intercept = (sum_y - slope * sum_x) / n
        
        # R-squared
        if sum_y2 - (sum_y ** 2) / n == 0:
            r_squared = 0
        else:
            ss_res = sum((y[i] - (slope * x[i] + intercept)) ** 2 for i in range(n))
            ss_tot = sum((y[i] - statistics.mean(y)) ** 2 for i in range(n))
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        
        # Trend direction
        if abs(slope) < 0.01:
            direction = "stable"
        elif slope > 0:
            direction = "increasing"
        else:
            direction = "decreasing"
        
        return {
            "slope": slope,
            "intercept": intercept,
            "r_squared": max(0, r_squared),  # Ensure non-negative
            "direction": direction,
            "trend_strength": self._classify_trend_strength(abs(slope), r_squared)
        }
    
    def _classify_trend(self, linear_trend: Dict[str, Any]) -> str:
        """Classify the overall trend."""
        slope = linear_trend.get("slope", 0)
        r_squared = linear_trend.get("r_squared", 0)
        
        if r_squared < 0.1:
            return "no_clear_trend"
        elif abs(slope) < 0.01:
            return "stable"
        elif slope > 0:
            if r_squared > 0.7:
                return "strong_upward"
            elif r_squared > 0.3:
                return "moderate_upward"
            else:
                return "weak_upward"
        else:
            if r_squared > 0.7:
                return "strong_downward"
            elif r_squared > 0.3:
                return "moderate_downward"
            else:
                return "weak_downward"
    
    def _classify_trend_strength(self, slope_abs: float, r_squared: float) -> str:
        """Classify trend strength."""
        if r_squared < 0.1:
            return "negligible"
        elif r_squared < 0.3:
            return "weak"
        elif r_squared < 0.7:
            return "moderate"
        else:
            return "strong"
    
    def _calculate_volatility(self, values: List[float]) -> Dict[str, Any]:
        """Calculate volatility metrics."""
        if len(values) < 2:
            return {"coefficient_of_variation": 0, "volatility_classification": "stable"}
        
        mean_val = statistics.mean(values)
        std_val = statistics.stdev(values)
        
        # Coefficient of variation
        cv = (std_val / mean_val) if mean_val != 0 else 0
        
        # Volatility classification
        if cv < 0.1:
            volatility_class = "low"
        elif cv < 0.3:
            volatility_class = "moderate"
        elif cv < 0.5:
            volatility_class = "high"
        else:
            volatility_class = "very_high"
        
        return {
            "standard_deviation": std_val,
            "coefficient_of_variation": cv,
            "volatility_classification": volatility_class
        }
    
    def _detect_change_points(self, timestamps: List[float], values: List[float]) -> List[Dict[str, Any]]:
        """Detect significant change points in the time series."""
        if len(values) < 10:  # Need minimum data
            return []
        
        change_points = []
        window_size = max(3, len(values) // 10)  # Adaptive window size
        
        for i in range(window_size, len(values) - window_size):
            # Compare before and after windows
            before_window = values[i-window_size:i]
            after_window = values[i:i+window_size]
            
            before_mean = statistics.mean(before_window)
            after_mean = statistics.mean(after_window)
            
            # Calculate change magnitude
            change_magnitude = abs(after_mean - before_mean)
            relative_change = change_magnitude / before_mean if before_mean != 0 else 0
            
            # Detect significant changes (>20% change)
            if relative_change > 0.2:
                change_points.append({
                    "timestamp": timestamps[i],
                    "index": i,
                    "before_mean": before_mean,
                    "after_mean": after_mean,
                    "change_magnitude": change_magnitude,
                    "relative_change_percent": relative_change * 100,
                    "change_type": "increase" if after_mean > before_mean else "decrease"
                })
        
        # Remove nearby change points (keep only the most significant)
        filtered_change_points = []
        for cp in change_points:
            # Check if there's a more significant change point nearby
            nearby_points = [
                other for other in change_points 
                if abs(other["timestamp"] - cp["timestamp"]) < 3600  # Within 1 hour
                and other["relative_change_percent"] > cp["relative_change_percent"]
            ]
            
            if not nearby_points:
                filtered_change_points.append(cp)
        
        return sorted(filtered_change_points, key=lambda x: x["timestamp"])
    
    async def _analyze_system_health_trend(self, metrics_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze overall system health trend."""
        try:
            # Create time windows for health analysis
            time_windows = self._create_time_windows(metrics_data, window_minutes=60)
            
            health_scores = []
            for window in time_windows:
                if not window:
                    continue
                
                # Calculate health score for this window
                total_requests = len(window)
                error_requests = sum(1 for m in window if m.get("status_code", 200) >= 400)
                error_rate = (error_requests / total_requests) * 100 if total_requests > 0 else 0
                
                # Average response time
                response_times = [m.get("response_time_ms", 0) for m in window if m.get("response_time_ms")]
                avg_response_time = statistics.mean(response_times) if response_times else 0
                
                # Average quality score
                quality_scores = [m.get("quality_score", 0) for m in window if m.get("quality_score")]
                avg_quality = statistics.mean(quality_scores) if quality_scores else 0.5
                
                # Calculate composite health score (0-100)
                health_score = 100
                health_score -= min(50, error_rate * 10)  # Error rate penalty
                health_score -= min(30, max(0, (avg_response_time - 1000) / 100))  # Latency penalty
                health_score += min(20, avg_quality * 20)  # Quality bonus
                
                health_scores.append({
                    "timestamp": window[0].get("timestamp", time.time()),
                    "health_score": max(0, min(100, health_score)),
                    "error_rate": error_rate,
                    "avg_response_time": avg_response_time,
                    "avg_quality": avg_quality,
                    "total_requests": total_requests
                })
            
            if len(health_scores) < 2:
                return {"error": "Insufficient data for system health trend"}
            
            # Analyze health trend
            timestamps = [hs["timestamp"] for hs in health_scores]
            scores = [hs["health_score"] for hs in health_scores]
            
            trend_analysis = self._calculate_linear_trend(timestamps, scores)
            
            return {
                "current_health_score": scores[-1],
                "average_health_score": statistics.mean(scores),
                "health_trend": trend_analysis,
                "health_classification": self._classify_health_trend(trend_analysis, scores[-1]),
                "data_points": len(health_scores),
                "health_history": health_scores[-10:]  # Last 10 data points
            }
        
        except Exception as e:
            logger.error(f"Error analyzing system health trend: {e}")
            return {"error": str(e)}
    
    def _classify_health_trend(self, trend_analysis: Dict[str, Any], current_score: float) -> str:
        """Classify system health trend."""
        direction = trend_analysis.get("direction", "stable")
        r_squared = trend_analysis.get("r_squared", 0)
        
        if current_score >= 90:
            base_health = "excellent"
        elif current_score >= 80:
            base_health = "good"
        elif current_score >= 70:
            base_health = "fair"
        elif current_score >= 60:
            base_health = "poor"
        else:
            base_health = "critical"
        
        if direction == "increasing" and r_squared > 0.3:
            trend_modifier = "improving"
        elif direction == "decreasing" and r_squared > 0.3:
            trend_modifier = "degrading"
        else:
            trend_modifier = "stable"
        
        return f"{base_health}_{trend_modifier}"
    
    async def _analyze_seasonal_patterns(self, metrics_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze seasonal patterns in the data."""
        if not self._seasonal_analysis:
            return {}
        
        try:
            # Group data by hour of day and day of week
            hourly_patterns = defaultdict(list)
            daily_patterns = defaultdict(list)
            
            for metric in metrics_data:
                timestamp = metric.get("timestamp", time.time())
                dt = datetime.fromtimestamp(timestamp)
                
                hour = dt.hour
                day_of_week = dt.weekday()  # 0 = Monday, 6 = Sunday
                
                # Collect various metrics
                hourly_patterns[hour].append({
                    "response_time": metric.get("response_time_ms", 0),
                    "cost": metric.get("cost_usd", 0),
                    "quality": metric.get("quality_score", 0),
                    "error": 1 if metric.get("status_code", 200) >= 400 else 0
                })
                
                daily_patterns[day_of_week].append({
                    "response_time": metric.get("response_time_ms", 0),
                    "cost": metric.get("cost_usd", 0),
                    "quality": metric.get("quality_score", 0),
                    "error": 1 if metric.get("status_code", 200) >= 400 else 0
                })
            
            seasonal_analysis = {}
            
            # Hourly patterns
            if hourly_patterns:
                hourly_stats = {}
                for hour, data in hourly_patterns.items():
                    if data:
                        hourly_stats[hour] = {
                            "request_count": len(data),
                            "avg_response_time": statistics.mean(d["response_time"] for d in data if d["response_time"] > 0),
                            "avg_cost": statistics.mean(d["cost"] for d in data if d["cost"] > 0),
                            "avg_quality": statistics.mean(d["quality"] for d in data if d["quality"] > 0),
                            "error_rate": statistics.mean(d["error"] for d in data) * 100
                        }
                
                # Find peak and low hours
                request_counts = {hour: stats["request_count"] for hour, stats in hourly_stats.items()}
                peak_hour = max(request_counts.items(), key=lambda x: x[1]) if request_counts else (0, 0)
                low_hour = min(request_counts.items(), key=lambda x: x[1]) if request_counts else (0, 0)
                
                seasonal_analysis["hourly_patterns"] = {
                    "hourly_stats": hourly_stats,
                    "peak_hour": {"hour": peak_hour[0], "requests": peak_hour[1]},
                    "low_hour": {"hour": low_hour[0], "requests": low_hour[1]},
                    "peak_to_low_ratio": peak_hour[1] / low_hour[1] if low_hour[1] > 0 else 0
                }
            
            # Daily patterns
            if daily_patterns:
                daily_stats = {}
                day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                
                for day, data in daily_patterns.items():
                    if data:
                        daily_stats[day_names[day]] = {
                            "request_count": len(data),
                            "avg_response_time": statistics.mean(d["response_time"] for d in data if d["response_time"] > 0),
                            "avg_cost": statistics.mean(d["cost"] for d in data if d["cost"] > 0),
                            "avg_quality": statistics.mean(d["quality"] for d in data if d["quality"] > 0),
                            "error_rate": statistics.mean(d["error"] for d in data) * 100
                        }
                
                seasonal_analysis["daily_patterns"] = daily_stats
            
            return seasonal_analysis
        
        except Exception as e:
            logger.error(f"Error analyzing seasonal patterns: {e}")
            return {"error": str(e)}
    
    async def _generate_forecasts(self, trends: Dict[str, Any]) -> Dict[str, Any]:
        """Generate forecasts based on trend analysis."""
        forecasts = {}
        
        for metric_type, trend_data in trends.items():
            if not trend_data or "slope" not in trend_data:
                continue
            
            try:
                # Simple linear forecast
                slope = trend_data["slope"]
                current_value = trend_data["current_value"]
                r_squared = trend_data.get("r_squared", 0)
                
                # Only forecast if trend is reasonably strong
                if r_squared > 0.1:
                    forecast_points = []
                    
                    # Generate forecast for specified horizon
                    for days_ahead in [1, 7, 14, 30]:
                        if days_ahead <= self._forecast_horizon_days:
                            hours_ahead = days_ahead * 24
                            forecasted_value = current_value + (slope * hours_ahead)
                            
                            # Calculate confidence (decreases with time)
                            confidence = max(0.1, r_squared * (1 - days_ahead / self._forecast_horizon_days))
                            
                            forecast_points.append({
                                "days_ahead": days_ahead,
                                "forecasted_value": forecasted_value,
                                "confidence": confidence,
                                "confidence_level": "high" if confidence > 0.7 else "medium" if confidence > 0.4 else "low"
                            })
                    
                    forecasts[metric_type] = {
                        "forecast_method": "linear_regression",
                        "base_value": current_value,
                        "trend_slope": slope,
                        "trend_strength": r_squared,
                        "forecast_points": forecast_points
                    }
            
            except Exception as e:
                logger.error(f"Error generating forecast for {metric_type}: {e}")
                continue
        
        return forecasts
    
    async def _generate_trend_insights(self, analysis_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate insights and recommendations based on trend analysis."""
        insights = []
        
        trends = analysis_result.get("trends", {})
        forecasts = analysis_result.get("forecasts", {})
        
        # Response time trend insights
        if "response_time" in trends:
            rt_trend = trends["response_time"]
            if rt_trend.get("direction") == "increasing" and rt_trend.get("r_squared", 0) > 0.3:
                insights.append({
                    "type": "performance_degradation",
                    "priority": "high",
                    "metric": "response_time",
                    "title": "Response Time Degradation Trend",
                    "description": f"Response times are trending upward with {rt_trend.get('trend_strength', 'unknown')} strength",
                    "current_value": rt_trend.get("current_value", 0),
                    "trend_direction": rt_trend.get("direction"),
                    "recommendations": [
                        "Investigate system performance bottlenecks",
                        "Consider scaling infrastructure resources",
                        "Review recent changes that might impact performance",
                        "Implement performance monitoring alerts"
                    ]
                })
        
        # Error rate trend insights
        if "error_rate" in trends:
            er_trend = trends["error_rate"]
            if er_trend.get("direction") == "increasing" and er_trend.get("current_value", 0) > 5:
                insights.append({
                    "type": "reliability_concern",
                    "priority": "critical",
                    "metric": "error_rate",
                    "title": "Rising Error Rate Trend",
                    "description": f"Error rates are increasing to {er_trend.get('current_value', 0):.1f}%",
                    "current_value": er_trend.get("current_value", 0),
                    "trend_direction": er_trend.get("direction"),
                    "recommendations": [
                        "Immediate investigation of error causes required",
                        "Implement circuit breaker patterns",
                        "Review provider health and status",
                        "Enhance error monitoring and alerting"
                    ]
                })
        
        # Cost trend insights
        if "cost" in trends:
            cost_trend = trends["cost"]
            if cost_trend.get("direction") == "increasing" and cost_trend.get("r_squared", 0) > 0.5:
                # Check forecast for cost projection
                cost_forecast = forecasts.get("cost", {})
                if cost_forecast:
                    monthly_projection = None
                    for fp in cost_forecast.get("forecast_points", []):
                        if fp["days_ahead"] == 30:
                            monthly_projection = fp["forecasted_value"]
                            break
                
                insights.append({
                    "type": "cost_optimization",
                    "priority": "medium",
                    "metric": "cost",
                    "title": "Rising Cost Trend",
                    "description": f"Costs are trending upward with strong correlation",
                    "current_value": cost_trend.get("current_value", 0),
                    "projected_monthly_cost": monthly_projection,
                    "trend_direction": cost_trend.get("direction"),
                    "recommendations": [
                        "Implement cost monitoring and budgets",
                        "Review model selection for cost efficiency",
                        "Consider usage optimization strategies",
                        "Negotiate volume discounts with providers"
                    ]
                })
        
        # Quality trend insights
        if "quality_score" in trends:
            quality_trend = trends["quality_score"]
            if quality_trend.get("direction") == "decreasing" and quality_trend.get("current_value", 1) < 0.7:
                insights.append({
                    "type": "quality_degradation",
                    "priority": "medium",
                    "metric": "quality_score",
                    "title": "Quality Score Decline",
                    "description": f"Quality scores are declining to {quality_trend.get('current_value', 0):.2f}",
                    "current_value": quality_trend.get("current_value", 0),
                    "trend_direction": quality_trend.get("direction"),
                    "recommendations": [
                        "Review model performance and selection criteria",
                        "Implement quality-aware routing",
                        "Analyze user feedback and satisfaction",
                        "Consider model fine-tuning or updates"
                    ]
                })
        
        # System health insights
        system_health = analysis_result.get("system_health_trend", {})
        if system_health:
            health_classification = system_health.get("health_classification", "")
            if "degrading" in health_classification or "critical" in health_classification:
                insights.append({
                    "type": "system_health",
                    "priority": "high",
                    "metric": "system_health",
                    "title": "System Health Degradation",
                    "description": f"Overall system health is {health_classification}",
                    "current_value": system_health.get("current_health_score", 0),
                    "trend_direction": system_health.get("health_trend", {}).get("direction", "unknown"),
                    "recommendations": [
                        "Comprehensive system health review required",
                        "Check all critical system components",
                        "Review recent deployments and changes",
                        "Implement enhanced monitoring and alerting"
                    ]
                })
        
        return insights
    
    def _create_time_windows(self, metrics: List[Dict[str, Any]], window_minutes: int = 60) -> List[List[Dict[str, Any]]]:
        """Create time windows from metrics data."""
        if not metrics:
            return []
        
        windows = []
        current_window = []
        window_start = metrics[0].get("timestamp", time.time())
        window_size_seconds = window_minutes * 60
        
        for metric in metrics:
            timestamp = metric.get("timestamp", time.time())
            
            if timestamp - window_start <= window_size_seconds:
                current_window.append(metric)
            else:
                if current_window:
                    windows.append(current_window)
                current_window = [metric]
                window_start = timestamp
        
        if current_window:
            windows.append(current_window)
        
        return windows
    
    def get_trend_summary(self, metric_type: str, days: int = 7) -> Optional[Dict[str, Any]]:
        """Get trend summary for a specific metric."""
        if metric_type not in self._trend_history:
            return None
        
        cutoff_time = time.time() - (days * 24 * 3600)
        recent_data = [
            point for point in self._trend_history[metric_type]
            if point["timestamp"] >= cutoff_time
        ]
        
        if len(recent_data) < 2:
            return None
        
        timestamps = [point["timestamp"] for point in recent_data]
        values = [point["value"] for point in recent_data]
        
        trend_analysis = self._calculate_linear_trend(timestamps, values)
        
        return {
            "metric_type": metric_type,
            "data_points": len(recent_data),
            "time_period_days": days,
            "current_value": values[-1],
            "trend_analysis": trend_analysis,
            "volatility": self._calculate_volatility(values)
        }
    
    def update_forecast_horizon(self, new_horizon_days: int) -> None:
        """Update forecast horizon."""
        self._forecast_horizon_days = max(1, min(90, new_horizon_days))
        logger.info(f"Updated forecast horizon to {self._forecast_horizon_days} days")