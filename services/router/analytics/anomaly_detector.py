"""Anomaly detection for enterprise AI platform analytics."""

import logging
import statistics
import time
from collections import defaultdict, deque
from typing import Any

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Detects anomalies in system behavior and performance metrics."""

    def __init__(self, config):
        self.config = config

        # Anomaly detection state
        self._baseline_metrics = {}
        self._anomaly_history = deque(maxlen=1000)
        self._detection_models = {}
        self._scalers = {}

        # Thresholds and parameters
        self._sensitivity = config.anomaly_sensitivity
        self._window_hours = config.anomaly_window_hours
        self._min_samples = config.anomaly_min_samples

        # Anomaly types
        self._anomaly_types = {
            "latency_spike": {"threshold_multiplier": 3.0, "metric": "response_time_ms"},
            "error_burst": {"threshold_multiplier": 5.0, "metric": "error_rate"},
            "cost_anomaly": {"threshold_multiplier": 4.0, "metric": "cost_usd"},
            "throughput_drop": {"threshold_multiplier": 0.3, "metric": "request_count"},
            "quality_degradation": {"threshold_multiplier": 0.7, "metric": "quality_score"},
        }

        logger.info("Anomaly detector initialized")

    async def detect_anomalies(
        self, metrics_data: list[dict[str, Any]], detection_types: list[str] | None = None
    ) -> dict[str, Any]:
        """Detect anomalies in metrics data."""
        if not metrics_data:
            return {"error": "No metrics data provided"}

        if len(metrics_data) < self._min_samples:
            return {"error": f"Insufficient data for anomaly detection (minimum {self._min_samples} samples required)"}

        try:
            # Filter recent data
            cutoff_time = time.time() - (self._window_hours * 3600)
            recent_metrics = [m for m in metrics_data if m.get("timestamp", 0) >= cutoff_time]

            if len(recent_metrics) < self._min_samples:
                return {"error": "Insufficient recent data for anomaly detection"}

            detection_results = {
                "analysis_timestamp": time.time(),
                "data_points_analyzed": len(recent_metrics),
                "detection_window_hours": self._window_hours,
                "anomalies_detected": [],
            }

            # Determine which detection types to run
            if detection_types is None:
                detection_types = list(self._anomaly_types.keys())

            # Statistical anomaly detection
            statistical_anomalies = await self._detect_statistical_anomalies(recent_metrics, detection_types)
            detection_results["statistical_anomalies"] = statistical_anomalies

            # Machine learning-based anomaly detection
            if len(recent_metrics) >= 50:  # Need more data for ML
                ml_anomalies = await self._detect_ml_anomalies(recent_metrics)
                detection_results["ml_anomalies"] = ml_anomalies

            # Pattern-based anomaly detection
            pattern_anomalies = await self._detect_pattern_anomalies(recent_metrics)
            detection_results["pattern_anomalies"] = pattern_anomalies

            # Combine all anomalies
            all_anomalies = []
            for anomaly_type in ["statistical_anomalies", "ml_anomalies", "pattern_anomalies"]:
                if anomaly_type in detection_results:
                    anomalies = detection_results[anomaly_type].get("anomalies", [])
                    for anomaly in anomalies:
                        anomaly["detection_method"] = anomaly_type
                        all_anomalies.append(anomaly)

            # Sort by severity and timestamp
            all_anomalies.sort(key=lambda x: (x.get("severity_score", 0), x.get("timestamp", 0)), reverse=True)
            detection_results["anomalies_detected"] = all_anomalies[:20]  # Top 20 anomalies

            # Anomaly summary
            detection_results["summary"] = {
                "total_anomalies": len(all_anomalies),
                "high_severity_anomalies": len([a for a in all_anomalies if a.get("severity_score", 0) > 0.8]),
                "anomaly_types_detected": list({a.get("anomaly_type") for a in all_anomalies}),
                "most_common_anomaly_type": max(
                    {a.get("anomaly_type") for a in all_anomalies},
                    key=lambda x: sum(1 for a in all_anomalies if a.get("anomaly_type") == x),
                )
                if all_anomalies
                else None,
            }

            # Store anomalies in history
            for anomaly in all_anomalies:
                self._anomaly_history.append(anomaly)

            return detection_results

        except Exception as e:
            logger.error(f"Error detecting anomalies: {e}")
            return {"error": str(e)}

    async def _detect_statistical_anomalies(
        self, metrics_data: list[dict[str, Any]], detection_types: list[str]
    ) -> dict[str, Any]:
        """Detect anomalies using statistical methods."""
        anomalies = []

        for anomaly_type in detection_types:
            if anomaly_type not in self._anomaly_types:
                continue

            config = self._anomaly_types[anomaly_type]
            metric_name = config["metric"]
            threshold_multiplier = config["threshold_multiplier"]

            # Extract metric values
            if metric_name == "error_rate":
                # Calculate error rate
                metric_values = []
                for i in range(0, len(metrics_data), 10):  # Group by 10s for error rate calculation
                    batch = metrics_data[i : i + 10]
                    errors = sum(1 for m in batch if m.get("status_code", 200) >= 400)
                    error_rate = (errors / len(batch)) * 100 if batch else 0
                    metric_values.append(
                        {
                            "timestamp": batch[0].get("timestamp", time.time()),
                            "value": error_rate,
                            "batch_size": len(batch),
                        }
                    )
            elif metric_name == "request_count":
                # Calculate throughput in time windows
                time_windows = self._create_time_windows(metrics_data, window_minutes=5)
                metric_values = []
                for window in time_windows:
                    if window:
                        metric_values.append(
                            {
                                "timestamp": window[0].get("timestamp", time.time()),
                                "value": len(window),
                                "window_size": len(window),
                            }
                        )
            else:
                # Direct metric extraction
                metric_values = []
                for metric in metrics_data:
                    value = metric.get(metric_name)
                    if value is not None:
                        metric_values.append(
                            {"timestamp": metric.get("timestamp", time.time()), "value": value, "metric_data": metric}
                        )

            if len(metric_values) < 10:  # Need minimum data
                continue

            # Calculate baseline statistics
            values = [mv["value"] for mv in metric_values]
            mean_value = statistics.mean(values)
            std_value = statistics.stdev(values) if len(values) > 1 else 0

            # Detect anomalies based on type
            if anomaly_type in ["latency_spike", "error_burst", "cost_anomaly"]:
                # High value anomalies
                threshold = mean_value + (std_value * threshold_multiplier)
                anomalous_points = [mv for mv in metric_values if mv["value"] > threshold]
            elif anomaly_type == "throughput_drop":
                # Low value anomalies
                threshold = mean_value * threshold_multiplier
                anomalous_points = [mv for mv in metric_values if mv["value"] < threshold]
            elif anomaly_type == "quality_degradation":
                # Low quality anomalies
                threshold = mean_value * threshold_multiplier
                anomalous_points = [mv for mv in metric_values if mv["value"] < threshold]
            else:
                continue

            # Create anomaly records
            for point in anomalous_points:
                severity_score = self._calculate_severity_score(point["value"], mean_value, std_value, anomaly_type)

                anomaly = {
                    "anomaly_type": anomaly_type,
                    "timestamp": point["timestamp"],
                    "metric_name": metric_name,
                    "anomalous_value": point["value"],
                    "baseline_mean": mean_value,
                    "baseline_std": std_value,
                    "threshold": threshold,
                    "severity_score": severity_score,
                    "deviation_factor": abs(point["value"] - mean_value) / std_value if std_value > 0 else 0,
                    "description": self._generate_anomaly_description(
                        anomaly_type, point["value"], mean_value, threshold
                    ),
                }

                anomalies.append(anomaly)

        return {"method": "statistical", "anomalies": anomalies, "detection_types_checked": detection_types}

    async def _detect_ml_anomalies(self, metrics_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Detect anomalies using machine learning methods."""
        try:
            # Prepare feature matrix
            features = []
            timestamps = []

            for metric in metrics_data:
                feature_vector = [
                    metric.get("response_time_ms", 0),
                    metric.get("cost_usd", 0),
                    metric.get("tokens_input", 0),
                    metric.get("tokens_output", 0),
                    metric.get("quality_score", 0),
                    1 if metric.get("status_code", 200) >= 400 else 0,  # Error flag
                    hash(metric.get("model_used", "")) % 1000,  # Model hash
                    hash(metric.get("user_id", "")) % 1000,  # User hash
                ]

                # Only include if we have some non-zero values
                if any(f > 0 for f in feature_vector[:5]):
                    features.append(feature_vector)
                    timestamps.append(metric.get("timestamp", time.time()))

            if len(features) < 50:
                return {"error": "Insufficient data for ML anomaly detection"}

            # Scale features
            scaler = StandardScaler()
            features_scaled = scaler.fit_transform(features)

            # Train Isolation Forest
            contamination = min(0.1, max(0.01, 1.0 - self._sensitivity))  # Convert sensitivity to contamination
            iso_forest = IsolationForest(contamination=contamination, random_state=42, n_estimators=100)
            anomaly_labels = iso_forest.fit_predict(features_scaled)
            anomaly_scores = iso_forest.score_samples(features_scaled)

            # Extract anomalies
            anomalies = []
            for i, (label, score) in enumerate(zip(anomaly_labels, anomaly_scores, strict=False)):
                if label == -1:  # Anomaly detected
                    # Find which features contributed most to the anomaly
                    feature_contributions = self._analyze_feature_contributions(features[i], features)

                    anomaly = {
                        "anomaly_type": "ml_detected",
                        "timestamp": timestamps[i],
                        "anomaly_score": float(score),
                        "severity_score": min(1.0, abs(score) / 0.5),  # Normalize to 0-1
                        "feature_contributions": feature_contributions,
                        "description": f"ML-detected anomaly with score {score:.3f}",
                        "feature_vector": features[i],
                    }

                    anomalies.append(anomaly)

            # Store model for future use
            self._detection_models["isolation_forest"] = iso_forest
            self._scalers["isolation_forest"] = scaler

            return {
                "method": "machine_learning",
                "model_type": "isolation_forest",
                "anomalies": anomalies,
                "contamination_rate": contamination,
                "total_samples": len(features),
            }

        except Exception as e:
            logger.error(f"Error in ML anomaly detection: {e}")
            return {"error": str(e)}

    async def _detect_pattern_anomalies(self, metrics_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Detect anomalies based on patterns and sequences."""
        anomalies = []

        # Sort by timestamp
        sorted_metrics = sorted(metrics_data, key=lambda x: x.get("timestamp", 0))

        # Detect sudden changes in patterns

        # 1. Sudden error rate spikes
        error_spike_anomalies = await self._detect_error_spikes(sorted_metrics)
        anomalies.extend(error_spike_anomalies)

        # 2. Unusual request patterns
        pattern_anomalies = await self._detect_unusual_patterns(sorted_metrics)
        anomalies.extend(pattern_anomalies)

        # 3. Sequential anomalies (e.g., cascading failures)
        sequential_anomalies = await self._detect_sequential_anomalies(sorted_metrics)
        anomalies.extend(sequential_anomalies)

        # 4. Temporal anomalies (unusual timing patterns)
        temporal_anomalies = await self._detect_temporal_anomalies(sorted_metrics)
        anomalies.extend(temporal_anomalies)

        return {
            "method": "pattern_based",
            "anomalies": anomalies,
            "pattern_types_checked": ["error_spikes", "unusual_patterns", "sequential", "temporal"],
        }

    async def _detect_error_spikes(self, sorted_metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Detect sudden spikes in error rates."""
        anomalies = []

        # Create 5-minute windows
        time_windows = self._create_time_windows(sorted_metrics, window_minutes=5)

        if len(time_windows) < 3:
            return anomalies

        # Calculate error rates for each window
        window_error_rates = []
        for window in time_windows:
            if window:
                errors = sum(1 for m in window if m.get("status_code", 200) >= 400)
                error_rate = (errors / len(window)) * 100
                window_error_rates.append(
                    {
                        "timestamp": window[0].get("timestamp", time.time()),
                        "error_rate": error_rate,
                        "total_requests": len(window),
                        "error_count": errors,
                    }
                )

        # Detect spikes
        for i in range(2, len(window_error_rates)):
            current_rate = window_error_rates[i]["error_rate"]
            prev_avg = statistics.mean([w["error_rate"] for w in window_error_rates[max(0, i - 5) : i]])

            # Spike detection: current rate is significantly higher than recent average
            if current_rate > prev_avg * 3 and current_rate > 10:  # At least 10% error rate
                anomaly = {
                    "anomaly_type": "error_spike",
                    "timestamp": window_error_rates[i]["timestamp"],
                    "current_error_rate": current_rate,
                    "baseline_error_rate": prev_avg,
                    "spike_magnitude": current_rate / prev_avg if prev_avg > 0 else float("inf"),
                    "severity_score": min(1.0, current_rate / 50),  # Normalize to 0-1
                    "description": f"Error rate spiked to {current_rate:.1f}% from baseline {prev_avg:.1f}%",
                    "affected_requests": window_error_rates[i]["total_requests"],
                }
                anomalies.append(anomaly)

        return anomalies

    async def _detect_unusual_patterns(self, sorted_metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Detect unusual request patterns."""
        anomalies = []

        # Analyze model usage patterns
        model_usage_windows = defaultdict(list)

        # Create hourly windows
        time_windows = self._create_time_windows(sorted_metrics, window_minutes=60)

        for window in time_windows:
            if not window:
                continue

            timestamp = window[0].get("timestamp", time.time())
            model_counts = defaultdict(int)

            for metric in window:
                model = metric.get("model_used")
                if model:
                    model_counts[model] += 1

            for model, count in model_counts.items():
                model_usage_windows[model].append(
                    {"timestamp": timestamp, "usage_count": count, "total_requests": len(window)}
                )

        # Detect unusual model usage patterns
        for model, usage_data in model_usage_windows.items():
            if len(usage_data) < 5:  # Need minimum data
                continue

            usage_counts = [u["usage_count"] for u in usage_data]
            mean_usage = statistics.mean(usage_counts)
            std_usage = statistics.stdev(usage_counts) if len(usage_counts) > 1 else 0

            # Find unusual spikes or drops
            for usage_point in usage_data[-3:]:  # Check last 3 data points
                deviation = abs(usage_point["usage_count"] - mean_usage)

                if std_usage > 0 and deviation > std_usage * 3:
                    anomaly_type = (
                        "model_usage_spike" if usage_point["usage_count"] > mean_usage else "model_usage_drop"
                    )

                    anomaly = {
                        "anomaly_type": anomaly_type,
                        "timestamp": usage_point["timestamp"],
                        "model": model,
                        "unusual_usage_count": usage_point["usage_count"],
                        "baseline_usage": mean_usage,
                        "deviation_factor": deviation / std_usage,
                        "severity_score": min(1.0, deviation / (std_usage * 5)),
                        "description": f"Unusual {model} usage: {usage_point['usage_count']} vs baseline {mean_usage:.1f}",
                    }
                    anomalies.append(anomaly)

        return anomalies

    async def _detect_sequential_anomalies(self, sorted_metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Detect sequential anomalies like cascading failures."""
        anomalies = []

        # Look for sequences of errors from the same user or model
        error_sequences = defaultdict(list)

        for metric in sorted_metrics:
            if metric.get("status_code", 200) >= 400:
                user_id = metric.get("user_id", "unknown")
                model = metric.get("model_used", "unknown")
                key = f"{user_id}:{model}"

                error_sequences[key].append(
                    {
                        "timestamp": metric.get("timestamp", time.time()),
                        "status_code": metric.get("status_code"),
                        "model": model,
                        "user_id": user_id,
                    }
                )

        # Detect cascading failures (multiple consecutive errors)
        for key, errors in error_sequences.items():
            if len(errors) < 3:  # Need at least 3 consecutive errors
                continue

            # Sort by timestamp
            errors.sort(key=lambda x: x["timestamp"])

            # Find consecutive error sequences
            consecutive_sequences = []
            current_sequence = [errors[0]]

            for i in range(1, len(errors)):
                time_diff = errors[i]["timestamp"] - errors[i - 1]["timestamp"]

                if time_diff < 300:  # Within 5 minutes
                    current_sequence.append(errors[i])
                else:
                    if len(current_sequence) >= 3:
                        consecutive_sequences.append(current_sequence)
                    current_sequence = [errors[i]]

            # Check final sequence
            if len(current_sequence) >= 3:
                consecutive_sequences.append(current_sequence)

            # Create anomalies for significant sequences
            for sequence in consecutive_sequences:
                if len(sequence) >= 3:
                    user_id, model = key.split(":", 1)

                    anomaly = {
                        "anomaly_type": "cascading_failure",
                        "timestamp": sequence[0]["timestamp"],
                        "user_id": user_id,
                        "model": model,
                        "consecutive_errors": len(sequence),
                        "time_span_minutes": (sequence[-1]["timestamp"] - sequence[0]["timestamp"]) / 60,
                        "severity_score": min(1.0, len(sequence) / 10),
                        "description": f"Cascading failure: {len(sequence)} consecutive errors for {user_id} using {model}",
                        "error_sequence": sequence,
                    }
                    anomalies.append(anomaly)

        return anomalies

    async def _detect_temporal_anomalies(self, sorted_metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Detect temporal anomalies in request patterns."""
        anomalies = []

        if len(sorted_metrics) < 100:  # Need sufficient data
            return anomalies

        # Analyze request timing patterns
        timestamps = [m.get("timestamp", time.time()) for m in sorted_metrics]

        # Calculate inter-arrival times
        inter_arrival_times = []
        for i in range(1, len(timestamps)):
            inter_arrival_times.append(timestamps[i] - timestamps[i - 1])

        if len(inter_arrival_times) < 50:
            return anomalies

        # Detect unusual gaps or bursts
        mean_interval = statistics.mean(inter_arrival_times)
        std_interval = statistics.stdev(inter_arrival_times) if len(inter_arrival_times) > 1 else 0

        # Find unusual intervals
        for i, interval in enumerate(inter_arrival_times):
            if std_interval > 0:
                z_score = abs(interval - mean_interval) / std_interval

                if z_score > 3:  # Significant deviation
                    anomaly_type = "request_burst" if interval < mean_interval * 0.1 else "request_gap"

                    anomaly = {
                        "anomaly_type": anomaly_type,
                        "timestamp": timestamps[i + 1],
                        "interval_seconds": interval,
                        "baseline_interval": mean_interval,
                        "z_score": z_score,
                        "severity_score": min(1.0, z_score / 5),
                        "description": f"Unusual request timing: {interval:.2f}s interval vs {mean_interval:.2f}s baseline",
                    }
                    anomalies.append(anomaly)

        return anomalies

    def _create_time_windows(
        self, metrics: list[dict[str, Any]], window_minutes: int = 5
    ) -> list[list[dict[str, Any]]]:
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

    def _calculate_severity_score(self, value: float, mean: float, std: float, anomaly_type: str) -> float:
        """Calculate severity score for an anomaly."""
        if std == 0:
            return 0.5  # Default severity when no variance

        z_score = abs(value - mean) / std

        # Normalize z-score to 0-1 range
        severity = min(1.0, z_score / 5.0)  # Cap at z-score of 5

        # Adjust based on anomaly type
        if anomaly_type in ["error_burst", "cascading_failure"]:
            severity *= 1.2  # Boost severity for critical anomalies
        elif anomaly_type in ["quality_degradation"]:
            severity *= 1.1  # Slightly boost quality issues

        return min(1.0, severity)

    def _generate_anomaly_description(self, anomaly_type: str, value: float, mean: float, threshold: float) -> str:
        """Generate human-readable description for anomaly."""
        descriptions = {
            "latency_spike": f"Response time spiked to {value:.0f}ms (baseline: {mean:.0f}ms, threshold: {threshold:.0f}ms)",
            "error_burst": f"Error rate increased to {value:.1f}% (baseline: {mean:.1f}%, threshold: {threshold:.1f}%)",
            "cost_anomaly": f"Cost anomaly detected: ${value:.4f} (baseline: ${mean:.4f}, threshold: ${threshold:.4f})",
            "throughput_drop": f"Throughput dropped to {value:.0f} requests (baseline: {mean:.0f}, threshold: {threshold:.0f})",
            "quality_degradation": f"Quality score dropped to {value:.2f} (baseline: {mean:.2f}, threshold: {threshold:.2f})",
        }

        return descriptions.get(anomaly_type, f"Anomaly detected: {value} (baseline: {mean}, threshold: {threshold})")

    def _analyze_feature_contributions(
        self, anomalous_features: list[float], all_features: list[list[float]]
    ) -> dict[str, float]:
        """Analyze which features contributed most to the anomaly."""
        feature_names = [
            "response_time_ms",
            "cost_usd",
            "tokens_input",
            "tokens_output",
            "quality_score",
            "error_flag",
            "model_hash",
            "user_hash",
        ]

        contributions = {}

        # Calculate how much each feature deviates from the norm
        for i, (feature_value, feature_name) in enumerate(zip(anomalous_features, feature_names, strict=False)):
            if i < len(feature_names):
                # Calculate feature statistics
                feature_values = [f[i] for f in all_features if len(f) > i]
                if feature_values:
                    mean_val = statistics.mean(feature_values)
                    std_val = statistics.stdev(feature_values) if len(feature_values) > 1 else 1

                    # Calculate normalized deviation
                    deviation = abs(feature_value - mean_val) / std_val if std_val > 0 else 0
                    contributions[feature_name] = min(1.0, deviation / 3.0)  # Normalize to 0-1

        return contributions

    async def predict_anomaly_likelihood(self, current_metrics: dict[str, Any]) -> dict[str, Any]:
        """Predict likelihood of anomaly for current metrics."""
        if "isolation_forest" not in self._detection_models:
            return {"error": "No trained model available for prediction"}

        try:
            model = self._detection_models["isolation_forest"]
            scaler = self._scalers["isolation_forest"]

            # Prepare feature vector
            feature_vector = [
                current_metrics.get("response_time_ms", 0),
                current_metrics.get("cost_usd", 0),
                current_metrics.get("tokens_input", 0),
                current_metrics.get("tokens_output", 0),
                current_metrics.get("quality_score", 0),
                1 if current_metrics.get("status_code", 200) >= 400 else 0,
                hash(current_metrics.get("model_used", "")) % 1000,
                hash(current_metrics.get("user_id", "")) % 1000,
            ]

            # Scale features
            feature_scaled = scaler.transform([feature_vector])

            # Predict
            prediction = model.predict(feature_scaled)[0]
            anomaly_score = model.score_samples(feature_scaled)[0]

            return {
                "is_anomaly": prediction == -1,
                "anomaly_score": float(anomaly_score),
                "likelihood_percentage": max(0, min(100, (0.5 - anomaly_score) * 200)),  # Convert to percentage
                "confidence": "high" if abs(anomaly_score) > 0.3 else "medium" if abs(anomaly_score) > 0.1 else "low",
            }

        except Exception as e:
            logger.error(f"Error predicting anomaly likelihood: {e}")
            return {"error": str(e)}

    def get_anomaly_history(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get recent anomaly history."""
        cutoff_time = time.time() - (hours * 3600)

        recent_anomalies = [anomaly for anomaly in self._anomaly_history if anomaly.get("timestamp", 0) >= cutoff_time]

        return sorted(recent_anomalies, key=lambda x: x.get("timestamp", 0), reverse=True)

    def update_sensitivity(self, new_sensitivity: float) -> None:
        """Update anomaly detection sensitivity."""
        self._sensitivity = max(0.5, min(0.99, new_sensitivity))
        logger.info(f"Updated anomaly detection sensitivity to {self._sensitivity}")

    def get_detection_stats(self) -> dict[str, Any]:
        """Get anomaly detection statistics."""
        recent_anomalies = self.get_anomaly_history(24)

        if not recent_anomalies:
            return {"total_anomalies": 0, "message": "No recent anomalies detected"}

        anomaly_types = defaultdict(int)
        severity_distribution = defaultdict(int)

        for anomaly in recent_anomalies:
            anomaly_types[anomaly.get("anomaly_type", "unknown")] += 1

            severity = anomaly.get("severity_score", 0)
            if severity > 0.8:
                severity_distribution["high"] += 1
            elif severity > 0.5:
                severity_distribution["medium"] += 1
            else:
                severity_distribution["low"] += 1

        return {
            "total_anomalies": len(recent_anomalies),
            "anomaly_types": dict(anomaly_types),
            "severity_distribution": dict(severity_distribution),
            "most_common_type": max(anomaly_types.items(), key=lambda x: x[1])[0] if anomaly_types else None,
            "average_severity": statistics.mean(a.get("severity_score", 0) for a in recent_anomalies),
        }
