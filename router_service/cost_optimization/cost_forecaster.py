"""Cost forecasting system with predictive analytics."""

import logging
import math
import statistics
import time
from typing import Any

from scipy import stats

logger = logging.getLogger(__name__)


class CostForecaster:
    """Predictive cost forecasting using statistical models."""

    def __init__(self, config=None):
        self.config = config

        # Historical data storage
        self._cost_history: list[tuple[float, float]] = []  # (timestamp, cost)
        self._usage_history: list[tuple[float, int]] = []  # (timestamp, token_count)

        # Model parameters
        self._trend_window = 168  # 7 days in hours
        self._seasonal_window = 24  # 24 hours for daily seasonality

        logger.info("Cost forecaster initialized")

    def add_data_point(self, cost_usd: float, token_count: int, timestamp: float | None = None) -> None:
        """Add a new data point for forecasting."""
        if timestamp is None:
            timestamp = time.time()

        self._cost_history.append((timestamp, cost_usd))
        self._usage_history.append((timestamp, token_count))

        # Keep only recent data (last 30 days)
        cutoff_time = timestamp - (30 * 24 * 3600)
        self._cost_history = [(ts, cost) for ts, cost in self._cost_history if ts > cutoff_time]
        self._usage_history = [(ts, tokens) for ts, tokens in self._usage_history if ts > cutoff_time]

    def forecast_cost(
        self, horizon_hours: int = 24, confidence_interval: float = 0.95, model_type: str = "linear"
    ) -> dict[str, Any]:
        """Generate cost forecast for the specified horizon."""
        if len(self._cost_history) < 10:
            return {
                "error": "Insufficient data for forecasting",
                "min_data_points": 10,
                "current_data_points": len(self._cost_history),
            }

        try:
            # Prepare data
            timestamps, costs = zip(*self._cost_history, strict=False)
            current_time = time.time()

            # Convert to hours from current time for easier modeling
            hours_from_now = [(ts - current_time) / 3600 for ts in timestamps]

            # Generate forecast based on model type
            if model_type == "linear":
                forecast_result = self._linear_forecast(hours_from_now, costs, horizon_hours, confidence_interval)
            elif model_type == "exponential":
                forecast_result = self._exponential_forecast(hours_from_now, costs, horizon_hours, confidence_interval)
            elif model_type == "seasonal":
                forecast_result = self._seasonal_forecast(hours_from_now, costs, horizon_hours, confidence_interval)
            else:
                return {"error": f"Unknown model type: {model_type}"}

            # Add metadata
            forecast_result.update(
                {
                    "model_type": model_type,
                    "data_points_used": len(self._cost_history),
                    "forecast_horizon_hours": horizon_hours,
                    "confidence_interval": confidence_interval,
                    "generated_at": current_time,
                }
            )

            return forecast_result

        except Exception as e:
            logger.error(f"Error generating cost forecast: {e}")
            return {"error": str(e)}

    def _linear_forecast(
        self, hours: list[float], costs: list[float], horizon_hours: int, confidence_interval: float
    ) -> dict[str, Any]:
        """Generate linear trend forecast."""
        # Perform linear regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(hours, costs)

        # Generate forecast points
        forecast_hours = list(range(1, horizon_hours + 1))
        forecast_costs = [slope * h + intercept for h in forecast_hours]

        # Calculate confidence intervals
        n = len(hours)
        t_val = stats.t.ppf((1 + confidence_interval) / 2, n - 2)

        # Standard error of prediction
        x_mean = statistics.mean(hours)
        ss_x = sum((x - x_mean) ** 2 for x in hours)

        confidence_bands = []
        for h in forecast_hours:
            se_pred = std_err * math.sqrt(1 + 1 / n + (h - x_mean) ** 2 / ss_x)
            margin = t_val * se_pred
            predicted_cost = slope * h + intercept

            confidence_bands.append(
                {
                    "hour": h,
                    "predicted_cost": predicted_cost,
                    "lower_bound": predicted_cost - margin,
                    "upper_bound": predicted_cost + margin,
                }
            )

        # Calculate total forecast
        total_forecast = sum(forecast_costs)
        total_lower = sum(band["lower_bound"] for band in confidence_bands)
        total_upper = sum(band["upper_bound"] for band in confidence_bands)

        return {
            "forecast_type": "linear",
            "total_forecast_usd": total_forecast,
            "confidence_bounds": {"lower": total_lower, "upper": total_upper},
            "hourly_forecast": confidence_bands,
            "model_stats": {
                "slope": slope,
                "intercept": intercept,
                "r_squared": r_value**2,
                "p_value": p_value,
                "standard_error": std_err,
            },
        }

    def _exponential_forecast(
        self, hours: list[float], costs: list[float], horizon_hours: int, confidence_interval: float
    ) -> dict[str, Any]:
        """Generate exponential growth/decay forecast."""
        try:
            # Transform to log space for exponential fitting
            log_costs = [math.log(max(cost, 1e-6)) for cost in costs]  # Avoid log(0)

            # Linear regression in log space
            slope, intercept, r_value, p_value, std_err = stats.linregress(hours, log_costs)

            # Generate forecast
            forecast_hours = list(range(1, horizon_hours + 1))
            forecast_costs = [math.exp(slope * h + intercept) for h in forecast_hours]

            # Confidence intervals (approximate)
            confidence_bands = []
            for h in forecast_hours:
                predicted_log = slope * h + intercept
                predicted_cost = math.exp(predicted_log)

                # Approximate confidence interval
                log_margin = 1.96 * std_err  # 95% CI approximation
                lower_bound = math.exp(predicted_log - log_margin)
                upper_bound = math.exp(predicted_log + log_margin)

                confidence_bands.append(
                    {
                        "hour": h,
                        "predicted_cost": predicted_cost,
                        "lower_bound": lower_bound,
                        "upper_bound": upper_bound,
                    }
                )

            total_forecast = sum(forecast_costs)
            total_lower = sum(band["lower_bound"] for band in confidence_bands)
            total_upper = sum(band["upper_bound"] for band in confidence_bands)

            return {
                "forecast_type": "exponential",
                "total_forecast_usd": total_forecast,
                "confidence_bounds": {"lower": total_lower, "upper": total_upper},
                "hourly_forecast": confidence_bands,
                "model_stats": {
                    "growth_rate": slope,
                    "base_level": math.exp(intercept),
                    "r_squared": r_value**2,
                    "p_value": p_value,
                },
            }

        except (ValueError, OverflowError) as e:
            # Fallback to linear if exponential fails
            logger.warning(f"Exponential forecast failed, falling back to linear: {e}")
            return self._linear_forecast(hours, costs, horizon_hours, confidence_interval)

    def _seasonal_forecast(
        self, hours: list[float], costs: list[float], horizon_hours: int, confidence_interval: float
    ) -> dict[str, Any]:
        """Generate seasonal forecast with daily patterns."""
        if len(hours) < 48:  # Need at least 2 days of data
            return self._linear_forecast(hours, costs, horizon_hours, confidence_interval)

        try:
            # Decompose into trend and seasonal components
            trend_component = self._extract_trend(hours, costs)
            seasonal_component = self._extract_seasonality(hours, costs, trend_component)

            # Generate forecast
            forecast_hours = list(range(1, horizon_hours + 1))
            forecast_costs = []
            confidence_bands = []

            for h in forecast_hours:
                # Trend forecast
                trend_value = self._predict_trend(h, trend_component)

                # Seasonal adjustment
                seasonal_value = self._predict_seasonality(h, seasonal_component)

                # Combined forecast
                predicted_cost = trend_value + seasonal_value

                # Simple confidence interval (could be improved)
                residuals = self._calculate_residuals(hours, costs, trend_component, seasonal_component)
                std_residual = statistics.stdev(residuals) if len(residuals) > 1 else 0
                margin = 1.96 * std_residual  # 95% CI

                confidence_bands.append(
                    {
                        "hour": h,
                        "predicted_cost": predicted_cost,
                        "trend_component": trend_value,
                        "seasonal_component": seasonal_value,
                        "lower_bound": predicted_cost - margin,
                        "upper_bound": predicted_cost + margin,
                    }
                )

                forecast_costs.append(predicted_cost)

            total_forecast = sum(forecast_costs)
            total_lower = sum(band["lower_bound"] for band in confidence_bands)
            total_upper = sum(band["upper_bound"] for band in confidence_bands)

            return {
                "forecast_type": "seasonal",
                "total_forecast_usd": total_forecast,
                "confidence_bounds": {"lower": total_lower, "upper": total_upper},
                "hourly_forecast": confidence_bands,
                "model_stats": {
                    "trend_strength": self._calculate_trend_strength(trend_component),
                    "seasonal_strength": self._calculate_seasonal_strength(seasonal_component),
                    "residual_std": statistics.stdev(residuals) if len(residuals) > 1 else 0,
                },
            }

        except Exception as e:
            logger.warning(f"Seasonal forecast failed, falling back to linear: {e}")
            return self._linear_forecast(hours, costs, horizon_hours, confidence_interval)

    def _extract_trend(self, hours: list[float], costs: list[float]) -> dict[str, float]:
        """Extract trend component using linear regression."""
        slope, intercept, r_value, _, _ = stats.linregress(hours, costs)
        return {"slope": slope, "intercept": intercept, "r_squared": r_value**2}

    def _extract_seasonality(
        self, hours: list[float], costs: list[float], trend_component: dict[str, float]
    ) -> dict[int, float]:
        """Extract daily seasonal patterns."""
        # Remove trend
        detrended_costs = [
            cost - (trend_component["slope"] * h + trend_component["intercept"])
            for h, cost in zip(hours, costs, strict=False)
        ]

        # Group by hour of day
        hourly_patterns = {}
        for h, detrended_cost in zip(hours, detrended_costs, strict=False):
            hour_of_day = int(h) % 24
            if hour_of_day not in hourly_patterns:
                hourly_patterns[hour_of_day] = []
            hourly_patterns[hour_of_day].append(detrended_cost)

        # Calculate average for each hour
        seasonal_pattern = {}
        for hour, values in hourly_patterns.items():
            seasonal_pattern[hour] = statistics.mean(values)

        return seasonal_pattern

    def _predict_trend(self, hour: float, trend_component: dict[str, float]) -> float:
        """Predict trend value for given hour."""
        return trend_component["slope"] * hour + trend_component["intercept"]

    def _predict_seasonality(self, hour: float, seasonal_component: dict[int, float]) -> float:
        """Predict seasonal adjustment for given hour."""
        hour_of_day = int(hour) % 24
        return seasonal_component.get(hour_of_day, 0.0)

    def _calculate_residuals(
        self,
        hours: list[float],
        costs: list[float],
        trend_component: dict[str, float],
        seasonal_component: dict[int, float],
    ) -> list[float]:
        """Calculate residuals for model validation."""
        residuals = []
        for h, cost in zip(hours, costs, strict=False):
            trend_pred = self._predict_trend(h, trend_component)
            seasonal_pred = self._predict_seasonality(h, seasonal_component)
            predicted = trend_pred + seasonal_pred
            residuals.append(cost - predicted)
        return residuals

    def _calculate_trend_strength(self, trend_component: dict[str, float]) -> float:
        """Calculate strength of trend component."""
        return abs(trend_component["slope"])

    def _calculate_seasonal_strength(self, seasonal_component: dict[int, float]) -> float:
        """Calculate strength of seasonal component."""
        if not seasonal_component:
            return 0.0
        values = list(seasonal_component.values())
        return statistics.stdev(values) if len(values) > 1 else 0.0

    def get_usage_forecast(self, horizon_hours: int = 24) -> dict[str, Any]:
        """Forecast token usage based on historical patterns."""
        if len(self._usage_history) < 10:
            return {
                "error": "Insufficient usage data for forecasting",
                "min_data_points": 10,
                "current_data_points": len(self._usage_history),
            }

        try:
            timestamps, token_counts = zip(*self._usage_history, strict=False)
            current_time = time.time()
            hours_from_now = [(ts - current_time) / 3600 for ts in timestamps]

            # Simple linear forecast for token usage
            slope, intercept, r_value, _, std_err = stats.linregress(hours_from_now, token_counts)

            forecast_hours = list(range(1, horizon_hours + 1))
            forecast_tokens = [max(0, slope * h + intercept) for h in forecast_hours]

            total_forecast_tokens = sum(forecast_tokens)

            return {
                "total_forecast_tokens": int(total_forecast_tokens),
                "hourly_forecast_tokens": [int(tokens) for tokens in forecast_tokens],
                "model_stats": {
                    "growth_rate_tokens_per_hour": slope,
                    "base_level_tokens": intercept,
                    "r_squared": r_value**2,
                },
                "forecast_horizon_hours": horizon_hours,
                "generated_at": current_time,
            }

        except Exception as e:
            logger.error(f"Error generating usage forecast: {e}")
            return {"error": str(e)}

    def get_cost_per_token_trend(self) -> dict[str, Any]:
        """Analyze cost per token trends."""
        if len(self._cost_history) < 10 or len(self._usage_history) < 10:
            return {"error": "Insufficient data for cost per token analysis"}

        try:
            # Align cost and usage data by timestamp
            dict(self._cost_history)
            dict(self._usage_history)

            # Find common timestamps (within 1 minute)
            cost_per_token_data = []
            for cost_ts, cost in self._cost_history:
                for usage_ts, tokens in self._usage_history:
                    if abs(cost_ts - usage_ts) <= 60 and tokens > 0:  # Within 1 minute and non-zero tokens
                        cost_per_token = cost / tokens
                        cost_per_token_data.append((cost_ts, cost_per_token))
                        break

            if len(cost_per_token_data) < 5:
                return {"error": "Insufficient aligned cost/usage data"}

            # Analyze trend
            timestamps, cost_per_token_values = zip(*cost_per_token_data, strict=False)
            current_time = time.time()
            hours_from_now = [(ts - current_time) / 3600 for ts in timestamps]

            slope, intercept, r_value, _, _ = stats.linregress(hours_from_now, cost_per_token_values)

            return {
                "current_cost_per_token": cost_per_token_values[-1],
                "trend_slope": slope,  # Change in cost per token per hour
                "trend_direction": "increasing" if slope > 0 else "decreasing" if slope < 0 else "stable",
                "r_squared": r_value**2,
                "data_points": len(cost_per_token_data),
                "analysis_period_hours": (timestamps[-1] - timestamps[0]) / 3600,
            }

        except Exception as e:
            logger.error(f"Error analyzing cost per token trend: {e}")
            return {"error": str(e)}

    def get_forecast_accuracy(self, actual_costs: list[tuple[float, float]]) -> dict[str, Any]:
        """Evaluate forecast accuracy against actual costs."""
        if not hasattr(self, "_last_forecast") or not actual_costs:
            return {"error": "No forecast or actual data available for accuracy evaluation"}

        try:
            # Compare forecast with actual costs
            forecast_values = [point["predicted_cost"] for point in self._last_forecast.get("hourly_forecast", [])]
            actual_values = [cost for _, cost in actual_costs[: len(forecast_values)]]

            if len(actual_values) < len(forecast_values):
                forecast_values = forecast_values[: len(actual_values)]

            # Calculate accuracy metrics
            errors = [abs(actual - forecast) for actual, forecast in zip(actual_values, forecast_values, strict=False)]
            relative_errors = [
                abs(actual - forecast) / max(actual, 0.001) * 100
                for actual, forecast in zip(actual_values, forecast_values, strict=False)
            ]

            mae = statistics.mean(errors)  # Mean Absolute Error
            mape = statistics.mean(relative_errors)  # Mean Absolute Percentage Error
            rmse = math.sqrt(statistics.mean([e**2 for e in errors]))  # Root Mean Square Error

            return {
                "mean_absolute_error": mae,
                "mean_absolute_percentage_error": mape,
                "root_mean_square_error": rmse,
                "forecast_points": len(forecast_values),
                "actual_points": len(actual_values),
                "accuracy_grade": self._get_accuracy_grade(mape),
            }

        except Exception as e:
            logger.error(f"Error calculating forecast accuracy: {e}")
            return {"error": str(e)}

    def _get_accuracy_grade(self, mape: float) -> str:
        """Get accuracy grade based on MAPE."""
        if mape <= 10:
            return "excellent"
        elif mape <= 20:
            return "good"
        elif mape <= 50:
            return "reasonable"
        else:
            return "poor"
