"""Performance analysis and optimization insights."""

import logging
import statistics
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class PerformanceAnalyzer:
    """Analyzes system performance and generates optimization insights."""

    def __init__(self, config):
        self.config = config

        # Performance tracking
        self._performance_history = deque(maxlen=10000)  # Keep last 10k data points
        self._baseline_metrics = {}
        self._performance_trends = {}

        # SLA tracking
        self._sla_violations = []
        self._sla_thresholds = {
            "latency_p95_ms": 5000,
            "latency_p99_ms": 10000,
            "error_rate_percent": 1.0,
            "availability_percent": 99.9,
        }

        logger.info("Performance analyzer initialized")

    async def analyze_performance_metrics(
        self, metrics_data: list[dict[str, Any]], time_window_hours: int = 24
    ) -> dict[str, Any]:
        """Analyze performance metrics and generate insights."""
        if not metrics_data:
            return {"error": "No metrics data to analyze"}

        try:
            # Filter by time window
            cutoff_time = time.time() - (time_window_hours * 3600)
            recent_metrics = [metric for metric in metrics_data if metric.get("timestamp", 0) >= cutoff_time]

            if not recent_metrics:
                return {"error": "No recent metrics in time window"}

            analysis_result = {
                "time_window_hours": time_window_hours,
                "total_data_points": len(recent_metrics),
                "analysis_timestamp": time.time(),
            }

            # Latency analysis
            if self.config.latency_analysis:
                analysis_result["latency_analysis"] = await self._analyze_latency(recent_metrics)

            # Throughput analysis
            if self.config.throughput_analysis:
                analysis_result["throughput_analysis"] = await self._analyze_throughput(recent_metrics)

            # Error rate analysis
            if self.config.error_rate_analysis:
                analysis_result["error_analysis"] = await self._analyze_error_rates(recent_metrics)

            # Quality analysis
            if self.config.quality_analysis:
                analysis_result["quality_analysis"] = await self._analyze_quality_metrics(recent_metrics)

            # SLA compliance analysis
            analysis_result["sla_analysis"] = await self._analyze_sla_compliance(recent_metrics)

            # Performance trends
            analysis_result["trends"] = await self._analyze_performance_trends(recent_metrics)

            # Resource utilization
            analysis_result["resource_utilization"] = await self._analyze_resource_utilization(recent_metrics)

            # Performance bottlenecks
            analysis_result["bottlenecks"] = await self._identify_bottlenecks(recent_metrics)

            # Optimization recommendations
            analysis_result["recommendations"] = await self._generate_optimization_recommendations(analysis_result)

            return analysis_result

        except Exception as e:
            logger.error(f"Error analyzing performance metrics: {e}")
            return {"error": str(e)}

    async def _analyze_latency(self, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze latency metrics and patterns."""
        latency_data = []

        for metric in metrics:
            if "response_time_ms" in metric:
                latency_data.append(
                    {
                        "timestamp": metric.get("timestamp", time.time()),
                        "latency_ms": metric["response_time_ms"],
                        "model": metric.get("model_used"),
                        "provider": metric.get("provider_used"),
                        "user_id": metric.get("user_id"),
                    }
                )

        if not latency_data:
            return {"error": "No latency data available"}

        latencies = [d["latency_ms"] for d in latency_data]

        analysis = {
            "total_requests": len(latencies),
            "statistics": {
                "mean_ms": statistics.mean(latencies),
                "median_ms": statistics.median(latencies),
                "p50_ms": np.percentile(latencies, 50),
                "p90_ms": np.percentile(latencies, 90),
                "p95_ms": np.percentile(latencies, 95),
                "p99_ms": np.percentile(latencies, 99),
                "min_ms": min(latencies),
                "max_ms": max(latencies),
                "std_dev_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
            },
        }

        # Latency by model
        model_latencies = defaultdict(list)
        for data in latency_data:
            if data["model"]:
                model_latencies[data["model"]].append(data["latency_ms"])

        model_analysis = {}
        for model, model_latencies_list in model_latencies.items():
            if model_latencies_list:
                model_analysis[model] = {
                    "mean_ms": statistics.mean(model_latencies_list),
                    "p95_ms": np.percentile(model_latencies_list, 95),
                    "request_count": len(model_latencies_list),
                }

        analysis["by_model"] = model_analysis

        # Latency by provider
        provider_latencies = defaultdict(list)
        for data in latency_data:
            if data["provider"]:
                provider_latencies[data["provider"]].append(data["latency_ms"])

        provider_analysis = {}
        for provider, provider_latencies_list in provider_latencies.items():
            if provider_latencies_list:
                provider_analysis[provider] = {
                    "mean_ms": statistics.mean(provider_latencies_list),
                    "p95_ms": np.percentile(provider_latencies_list, 95),
                    "request_count": len(provider_latencies_list),
                }

        analysis["by_provider"] = provider_analysis

        # Latency distribution
        fast_requests = sum(1 for latency in latencies if latency < 1000)  # < 1s
        medium_requests = sum(1 for latency in latencies if 1000 <= latency < 5000)  # 1-5s
        slow_requests = sum(1 for latency in latencies if latency >= 5000)  # >= 5s

        analysis["distribution"] = {
            "fast_requests_lt_1s": fast_requests,
            "medium_requests_1_5s": medium_requests,
            "slow_requests_gte_5s": slow_requests,
            "fast_percentage": (fast_requests / len(latencies)) * 100,
            "slow_percentage": (slow_requests / len(latencies)) * 100,
        }

        # SLA violations
        sla_violations = sum(1 for latency in latencies if latency > self._sla_thresholds["latency_p95_ms"])
        analysis["sla_violations"] = {
            "count": sla_violations,
            "percentage": (sla_violations / len(latencies)) * 100,
            "threshold_ms": self._sla_thresholds["latency_p95_ms"],
        }

        return analysis

    async def _analyze_throughput(self, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze throughput metrics and capacity."""
        # Group metrics by time buckets (e.g., per minute)
        time_buckets = defaultdict(int)

        for metric in metrics:
            timestamp = metric.get("timestamp", time.time())
            # Round to minute
            minute_bucket = int(timestamp // 60) * 60
            time_buckets[minute_bucket] += 1

        if not time_buckets:
            return {"error": "No throughput data available"}

        throughput_values = list(time_buckets.values())

        analysis = {
            "time_buckets_analyzed": len(time_buckets),
            "statistics": {
                "mean_requests_per_minute": statistics.mean(throughput_values),
                "median_requests_per_minute": statistics.median(throughput_values),
                "max_requests_per_minute": max(throughput_values),
                "min_requests_per_minute": min(throughput_values),
                "std_dev": statistics.stdev(throughput_values) if len(throughput_values) > 1 else 0,
            },
        }

        # Peak analysis
        sorted_buckets = sorted(time_buckets.items(), key=lambda x: x[1], reverse=True)
        peak_times = sorted_buckets[:5]  # Top 5 peak times

        analysis["peak_analysis"] = {
            "peak_times": [
                {
                    "timestamp": timestamp,
                    "datetime": datetime.fromtimestamp(timestamp).isoformat(),
                    "requests_per_minute": count,
                }
                for timestamp, count in peak_times
            ],
            "peak_to_average_ratio": max(throughput_values) / statistics.mean(throughput_values)
            if throughput_values
            else 0,
        }

        # Capacity analysis
        p95_throughput = np.percentile(throughput_values, 95)
        analysis["capacity_analysis"] = {
            "p95_requests_per_minute": p95_throughput,
            "estimated_hourly_capacity": p95_throughput * 60,
            "estimated_daily_capacity": p95_throughput * 60 * 24,
        }

        return analysis

    async def _analyze_error_rates(self, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze error rates and patterns."""
        total_requests = len(metrics)
        error_requests = []

        for metric in metrics:
            status_code = metric.get("status_code", 200)
            if status_code >= 400:
                error_requests.append(
                    {
                        "timestamp": metric.get("timestamp", time.time()),
                        "status_code": status_code,
                        "model": metric.get("model_used"),
                        "provider": metric.get("provider_used"),
                        "error_type": self._categorize_error(status_code),
                    }
                )

        error_count = len(error_requests)
        error_rate = (error_count / total_requests) * 100 if total_requests > 0 else 0

        analysis = {
            "total_requests": total_requests,
            "error_requests": error_count,
            "error_rate_percent": error_rate,
            "success_rate_percent": 100 - error_rate,
        }

        if error_requests:
            # Error distribution by status code
            status_distribution = defaultdict(int)
            for error in error_requests:
                status_distribution[error["status_code"]] += 1

            analysis["error_distribution"] = dict(status_distribution)

            # Error distribution by type
            type_distribution = defaultdict(int)
            for error in error_requests:
                type_distribution[error["error_type"]] += 1

            analysis["error_types"] = dict(type_distribution)

            # Error distribution by model
            model_errors = defaultdict(int)
            model_totals = defaultdict(int)

            for metric in metrics:
                model = metric.get("model_used")
                if model:
                    model_totals[model] += 1
                    if metric.get("status_code", 200) >= 400:
                        model_errors[model] += 1

            model_error_rates = {}
            for model in model_totals:
                error_rate = (model_errors[model] / model_totals[model]) * 100
                model_error_rates[model] = {
                    "error_count": model_errors[model],
                    "total_requests": model_totals[model],
                    "error_rate_percent": error_rate,
                }

            analysis["by_model"] = model_error_rates

            # Error distribution by provider
            provider_errors = defaultdict(int)
            provider_totals = defaultdict(int)

            for metric in metrics:
                provider = metric.get("provider_used")
                if provider:
                    provider_totals[provider] += 1
                    if metric.get("status_code", 200) >= 400:
                        provider_errors[provider] += 1

            provider_error_rates = {}
            for provider in provider_totals:
                error_rate = (provider_errors[provider] / provider_totals[provider]) * 100
                provider_error_rates[provider] = {
                    "error_count": provider_errors[provider],
                    "total_requests": provider_totals[provider],
                    "error_rate_percent": error_rate,
                }

            analysis["by_provider"] = provider_error_rates

        # SLA compliance
        sla_threshold = self._sla_thresholds["error_rate_percent"]
        analysis["sla_compliance"] = {
            "meets_sla": error_rate <= sla_threshold,
            "sla_threshold_percent": sla_threshold,
            "deviation_from_sla": error_rate - sla_threshold,
        }

        return analysis

    def _categorize_error(self, status_code: int) -> str:
        """Categorize error by status code."""
        if 400 <= status_code < 500:
            return "client_error"
        elif 500 <= status_code < 600:
            return "server_error"
        else:
            return "unknown_error"

    async def _analyze_quality_metrics(self, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze quality metrics and satisfaction scores."""
        quality_data = []

        for metric in metrics:
            quality_score = metric.get("quality_score")
            if quality_score is not None:
                quality_data.append(
                    {
                        "timestamp": metric.get("timestamp", time.time()),
                        "quality_score": quality_score,
                        "model": metric.get("model_used"),
                        "provider": metric.get("provider_used"),
                    }
                )

        if not quality_data:
            return {"error": "No quality data available"}

        quality_scores = [d["quality_score"] for d in quality_data]

        analysis = {
            "total_requests_with_quality": len(quality_scores),
            "statistics": {
                "mean_score": statistics.mean(quality_scores),
                "median_score": statistics.median(quality_scores),
                "p25_score": np.percentile(quality_scores, 25),
                "p75_score": np.percentile(quality_scores, 75),
                "p95_score": np.percentile(quality_scores, 95),
                "min_score": min(quality_scores),
                "max_score": max(quality_scores),
                "std_dev": statistics.stdev(quality_scores) if len(quality_scores) > 1 else 0,
            },
        }

        # Quality distribution
        high_quality = sum(1 for s in quality_scores if s >= 0.8)
        medium_quality = sum(1 for s in quality_scores if 0.6 <= s < 0.8)
        low_quality = sum(1 for s in quality_scores if s < 0.6)

        analysis["quality_distribution"] = {
            "high_quality_requests": high_quality,
            "medium_quality_requests": medium_quality,
            "low_quality_requests": low_quality,
            "high_quality_percentage": (high_quality / len(quality_scores)) * 100,
            "low_quality_percentage": (low_quality / len(quality_scores)) * 100,
        }

        # Quality by model
        model_quality = defaultdict(list)
        for data in quality_data:
            if data["model"]:
                model_quality[data["model"]].append(data["quality_score"])

        model_analysis = {}
        for model, scores in model_quality.items():
            if scores:
                model_analysis[model] = {
                    "mean_score": statistics.mean(scores),
                    "median_score": statistics.median(scores),
                    "request_count": len(scores),
                    "high_quality_percentage": (sum(1 for s in scores if s >= 0.8) / len(scores)) * 100,
                }

        analysis["by_model"] = model_analysis

        return analysis

    async def _analyze_sla_compliance(self, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze SLA compliance across different metrics."""
        sla_analysis = {"sla_thresholds": self._sla_thresholds, "compliance_summary": {}}

        # Latency SLA compliance
        latencies = [m.get("response_time_ms", 0) for m in metrics if m.get("response_time_ms")]
        if latencies:
            p95_latency = np.percentile(latencies, 95)
            latency_violations = sum(1 for latency in latencies if latency > self._sla_thresholds["latency_p95_ms"])

            sla_analysis["compliance_summary"]["latency"] = {
                "meets_sla": p95_latency <= self._sla_thresholds["latency_p95_ms"],
                "p95_latency_ms": p95_latency,
                "threshold_ms": self._sla_thresholds["latency_p95_ms"],
                "violation_count": latency_violations,
                "violation_percentage": (latency_violations / len(latencies)) * 100,
            }

        # Error rate SLA compliance
        total_requests = len(metrics)
        error_requests = sum(1 for m in metrics if m.get("status_code", 200) >= 400)
        error_rate = (error_requests / total_requests) * 100 if total_requests > 0 else 0

        sla_analysis["compliance_summary"]["error_rate"] = {
            "meets_sla": error_rate <= self._sla_thresholds["error_rate_percent"],
            "current_error_rate_percent": error_rate,
            "threshold_percent": self._sla_thresholds["error_rate_percent"],
            "error_count": error_requests,
            "total_requests": total_requests,
        }

        # Overall SLA compliance
        compliance_checks = [
            sla_analysis["compliance_summary"].get("latency", {}).get("meets_sla", True),
            sla_analysis["compliance_summary"].get("error_rate", {}).get("meets_sla", True),
        ]

        sla_analysis["overall_compliance"] = {
            "meets_all_slas": all(compliance_checks),
            "sla_compliance_percentage": (sum(compliance_checks) / len(compliance_checks)) * 100,
        }

        return sla_analysis

    async def _analyze_performance_trends(self, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze performance trends over time."""
        if len(metrics) < 10:  # Need minimum data for trend analysis
            return {"error": "Insufficient data for trend analysis"}

        # Sort metrics by timestamp
        sorted_metrics = sorted(metrics, key=lambda x: x.get("timestamp", 0))

        # Split into time windows for trend analysis
        time_windows = self._create_time_windows(sorted_metrics, window_size_minutes=60)

        trends = {}

        # Latency trend
        latency_trend = []
        for window in time_windows:
            latencies = [m.get("response_time_ms", 0) for m in window if m.get("response_time_ms")]
            if latencies:
                latency_trend.append(
                    {
                        "timestamp": window[0].get("timestamp", 0),
                        "mean_latency_ms": statistics.mean(latencies),
                        "p95_latency_ms": np.percentile(latencies, 95),
                    }
                )

        if len(latency_trend) >= 2:
            trends["latency"] = {
                "data_points": latency_trend,
                "trend_direction": self._calculate_trend_direction(
                    [point["mean_latency_ms"] for point in latency_trend]
                ),
                "improvement_percentage": self._calculate_improvement_percentage(
                    [point["mean_latency_ms"] for point in latency_trend]
                ),
            }

        # Throughput trend
        throughput_trend = []
        for window in time_windows:
            throughput_trend.append({"timestamp": window[0].get("timestamp", 0), "requests_count": len(window)})

        if len(throughput_trend) >= 2:
            trends["throughput"] = {
                "data_points": throughput_trend,
                "trend_direction": self._calculate_trend_direction(
                    [point["requests_count"] for point in throughput_trend]
                ),
                "improvement_percentage": self._calculate_improvement_percentage(
                    [point["requests_count"] for point in throughput_trend]
                ),
            }

        # Error rate trend
        error_rate_trend = []
        for window in time_windows:
            total_requests = len(window)
            error_requests = sum(1 for m in window if m.get("status_code", 200) >= 400)
            error_rate = (error_requests / total_requests) * 100 if total_requests > 0 else 0

            error_rate_trend.append(
                {
                    "timestamp": window[0].get("timestamp", 0),
                    "error_rate_percent": error_rate,
                    "error_count": error_requests,
                    "total_requests": total_requests,
                }
            )

        if len(error_rate_trend) >= 2:
            trends["error_rate"] = {
                "data_points": error_rate_trend,
                "trend_direction": self._calculate_trend_direction(
                    [point["error_rate_percent"] for point in error_rate_trend]
                ),
                "improvement_percentage": self._calculate_improvement_percentage(
                    [point["error_rate_percent"] for point in error_rate_trend], lower_is_better=True
                ),
            }

        return trends

    def _create_time_windows(
        self, metrics: list[dict[str, Any]], window_size_minutes: int = 60
    ) -> list[list[dict[str, Any]]]:
        """Create time windows for trend analysis."""
        if not metrics:
            return []

        windows = []
        current_window = []
        window_start = metrics[0].get("timestamp", 0)
        window_size_seconds = window_size_minutes * 60

        for metric in metrics:
            timestamp = metric.get("timestamp", 0)

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

    def _calculate_trend_direction(self, values: list[float]) -> str:
        """Calculate trend direction from a series of values."""
        if len(values) < 2:
            return "insufficient_data"

        # Simple linear trend calculation
        x = list(range(len(values)))
        n = len(values)

        sum_x = sum(x)
        sum_y = sum(values)
        sum_xy = sum(x[i] * values[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))

        # Calculate slope
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x**2)

        if abs(slope) < 0.01:  # Threshold for "stable"
            return "stable"
        elif slope > 0:
            return "increasing"
        else:
            return "decreasing"

    def _calculate_improvement_percentage(self, values: list[float], lower_is_better: bool = False) -> float:
        """Calculate improvement percentage between first and last values."""
        if len(values) < 2:
            return 0.0

        first_value = values[0]
        last_value = values[-1]

        if first_value == 0:
            return 0.0

        change_percent = ((last_value - first_value) / first_value) * 100

        # For metrics where lower is better (like error rate), invert the improvement
        if lower_is_better:
            change_percent = -change_percent

        return change_percent

    async def _analyze_resource_utilization(self, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze resource utilization patterns."""
        utilization = {"token_utilization": {}, "cost_utilization": {}, "model_utilization": {}}

        # Token utilization analysis
        total_input_tokens = sum(m.get("tokens_input", 0) for m in metrics)
        total_output_tokens = sum(m.get("tokens_output", 0) for m in metrics)

        if total_input_tokens > 0 or total_output_tokens > 0:
            utilization["token_utilization"] = {
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
                "input_output_ratio": total_output_tokens / total_input_tokens if total_input_tokens > 0 else 0,
                "avg_tokens_per_request": (total_input_tokens + total_output_tokens) / len(metrics) if metrics else 0,
            }

        # Cost utilization analysis
        total_cost = sum(m.get("cost_usd", 0) for m in metrics)
        if total_cost > 0:
            utilization["cost_utilization"] = {
                "total_cost_usd": total_cost,
                "avg_cost_per_request": total_cost / len(metrics) if metrics else 0,
                "cost_per_token": total_cost / (total_input_tokens + total_output_tokens)
                if (total_input_tokens + total_output_tokens) > 0
                else 0,
            }

        # Model utilization analysis
        model_usage = defaultdict(int)
        model_costs = defaultdict(float)

        for metric in metrics:
            model = metric.get("model_used")
            if model:
                model_usage[model] += 1
                model_costs[model] += metric.get("cost_usd", 0)

        if model_usage:
            utilization["model_utilization"] = {
                "total_models_used": len(model_usage),
                "model_distribution": dict(model_usage),
                "model_cost_distribution": dict(model_costs),
                "most_used_model": max(model_usage.items(), key=lambda x: x[1])[0],
                "most_expensive_model": max(model_costs.items(), key=lambda x: x[1])[0] if model_costs else None,
            }

        return utilization

    async def _identify_bottlenecks(self, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        """Identify performance bottlenecks."""
        bottlenecks = {
            "latency_bottlenecks": [],
            "error_bottlenecks": [],
            "cost_bottlenecks": [],
            "capacity_bottlenecks": [],
        }

        # Latency bottlenecks
        latencies = [(m.get("response_time_ms", 0), m) for m in metrics if m.get("response_time_ms")]
        if latencies:
            # Find requests with high latency
            p95_latency = np.percentile([lat_val[0] for lat_val in latencies], 95)
            high_latency_requests = [metric for lat_val, metric in latencies if lat_val > p95_latency * 1.5]

            if high_latency_requests:
                # Analyze patterns in high latency requests
                model_latency_issues = defaultdict(int)
                provider_latency_issues = defaultdict(int)

                for req in high_latency_requests:
                    model = req.get("model_used")
                    provider = req.get("provider_used")
                    if model:
                        model_latency_issues[model] += 1
                    if provider:
                        provider_latency_issues[provider] += 1

                bottlenecks["latency_bottlenecks"] = {
                    "high_latency_requests": len(high_latency_requests),
                    "p95_threshold_ms": p95_latency,
                    "problematic_models": dict(model_latency_issues),
                    "problematic_providers": dict(provider_latency_issues),
                }

        # Error bottlenecks
        error_requests = [m for m in metrics if m.get("status_code", 200) >= 400]
        if error_requests:
            model_error_issues = defaultdict(int)
            provider_error_issues = defaultdict(int)
            error_type_issues = defaultdict(int)

            for req in error_requests:
                model = req.get("model_used")
                provider = req.get("provider_used")
                status_code = req.get("status_code", 500)

                if model:
                    model_error_issues[model] += 1
                if provider:
                    provider_error_issues[provider] += 1
                error_type_issues[self._categorize_error(status_code)] += 1

            bottlenecks["error_bottlenecks"] = {
                "total_error_requests": len(error_requests),
                "error_rate_percent": (len(error_requests) / len(metrics)) * 100,
                "problematic_models": dict(model_error_issues),
                "problematic_providers": dict(provider_error_issues),
                "error_types": dict(error_type_issues),
            }

        # Cost bottlenecks
        costs = [(m.get("cost_usd", 0), m) for m in metrics if m.get("cost_usd")]
        if costs:
            p95_cost = np.percentile([c[0] for c in costs], 95)
            high_cost_requests = [m for c, m in costs if c > p95_cost * 1.5]

            if high_cost_requests:
                model_cost_issues = defaultdict(float)
                provider_cost_issues = defaultdict(float)

                for req in high_cost_requests:
                    model = req.get("model_used")
                    provider = req.get("provider_used")
                    cost = req.get("cost_usd", 0)

                    if model:
                        model_cost_issues[model] += cost
                    if provider:
                        provider_cost_issues[provider] += cost

                bottlenecks["cost_bottlenecks"] = {
                    "high_cost_requests": len(high_cost_requests),
                    "p95_cost_threshold_usd": p95_cost,
                    "expensive_models": dict(model_cost_issues),
                    "expensive_providers": dict(provider_cost_issues),
                }

        return bottlenecks

    async def _generate_optimization_recommendations(self, analysis_result: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate optimization recommendations based on analysis."""
        recommendations = []

        # Latency optimization recommendations
        latency_analysis = analysis_result.get("latency_analysis", {})
        if latency_analysis:
            stats = latency_analysis.get("statistics", {})
            p95_latency = stats.get("p95_ms", 0)

            if p95_latency > 5000:  # > 5 seconds
                recommendations.append(
                    {
                        "type": "latency_optimization",
                        "priority": "high",
                        "title": "High Latency Detected",
                        "description": f"P95 latency is {p95_latency:.0f}ms, which exceeds recommended thresholds",
                        "recommendations": [
                            "Consider implementing request caching for frequently used prompts",
                            "Evaluate switching to faster models for non-critical requests",
                            "Implement request batching where possible",
                            "Consider using streaming responses for long-running requests",
                        ],
                    }
                )

            # Model-specific latency recommendations
            by_model = latency_analysis.get("by_model", {})
            slow_models = {model: data for model, data in by_model.items() if data.get("p95_ms", 0) > 8000}

            if slow_models:
                recommendations.append(
                    {
                        "type": "model_optimization",
                        "priority": "medium",
                        "title": "Slow Models Identified",
                        "description": f"Models with high latency: {', '.join(slow_models.keys())}",
                        "recommendations": [
                            "Consider alternative models with better latency characteristics",
                            "Implement model-specific timeout configurations",
                            "Use faster models for time-sensitive requests",
                        ],
                    }
                )

        # Error rate optimization recommendations
        error_analysis = analysis_result.get("error_analysis", {})
        if error_analysis:
            error_rate = error_analysis.get("error_rate_percent", 0)

            if error_rate > 5:  # > 5% error rate
                recommendations.append(
                    {
                        "type": "reliability_optimization",
                        "priority": "high",
                        "title": "High Error Rate Detected",
                        "description": f"Current error rate is {error_rate:.1f}%, which exceeds acceptable thresholds",
                        "recommendations": [
                            "Implement automatic retry logic with exponential backoff",
                            "Add circuit breaker patterns for failing providers",
                            "Improve input validation to reduce client errors",
                            "Monitor and alert on error rate spikes",
                        ],
                    }
                )

            # Provider-specific error recommendations
            by_provider = error_analysis.get("by_provider", {})
            problematic_providers = {
                provider: data for provider, data in by_provider.items() if data.get("error_rate_percent", 0) > 10
            }

            if problematic_providers:
                recommendations.append(
                    {
                        "type": "provider_optimization",
                        "priority": "medium",
                        "title": "Problematic Providers Identified",
                        "description": f"Providers with high error rates: {', '.join(problematic_providers.keys())}",
                        "recommendations": [
                            "Reduce traffic to problematic providers",
                            "Implement provider health checks",
                            "Consider alternative providers for affected models",
                        ],
                    }
                )

        # Cost optimization recommendations
        if "bottlenecks" in analysis_result:
            cost_bottlenecks = analysis_result["bottlenecks"].get("cost_bottlenecks", {})
            if cost_bottlenecks:
                recommendations.append(
                    {
                        "type": "cost_optimization",
                        "priority": "medium",
                        "title": "Cost Optimization Opportunities",
                        "description": "High-cost requests identified that may benefit from optimization",
                        "recommendations": [
                            "Implement request size limits to prevent excessive token usage",
                            "Use cheaper models for non-critical requests",
                            "Implement cost-aware routing to balance cost and quality",
                            "Add cost monitoring and alerting",
                        ],
                    }
                )

        # SLA compliance recommendations
        sla_analysis = analysis_result.get("sla_analysis", {})
        if sla_analysis:
            overall_compliance = sla_analysis.get("overall_compliance", {})
            if not overall_compliance.get("meets_all_slas", True):
                recommendations.append(
                    {
                        "type": "sla_compliance",
                        "priority": "high",
                        "title": "SLA Violations Detected",
                        "description": "System is not meeting one or more SLA requirements",
                        "recommendations": [
                            "Review and adjust SLA thresholds if necessary",
                            "Implement performance monitoring and alerting",
                            "Consider scaling resources during peak usage",
                            "Implement graceful degradation strategies",
                        ],
                    }
                )

        return recommendations

    def update_sla_thresholds(self, new_thresholds: dict[str, float]) -> None:
        """Update SLA thresholds."""
        self._sla_thresholds.update(new_thresholds)
        logger.info(f"Updated SLA thresholds: {self._sla_thresholds}")

    def get_sla_thresholds(self) -> dict[str, float]:
        """Get current SLA thresholds."""
        return self._sla_thresholds.copy()
