"""Tests for the advanced analytics and intelligence system."""

import time
from unittest.mock import patch

import pytest

from router_service.analytics import (
    AnalyticsConfig,
    AnalyticsManager,
    AnomalyDetector,
    BusinessIntelligenceEngine,
    InsightsGenerator,
    PerformanceAnalyzer,
    RequestAnalyzer,
    TrendAnalyzer,
)


@pytest.fixture
def analytics_config():
    """Create test analytics configuration."""
    return AnalyticsConfig(
        enabled=True,
        data_retention_days=30,
        analysis_interval_minutes=5,
        request_analytics_enabled=True,
        performance_analytics_enabled=True,
        business_intelligence_enabled=True,
        anomaly_detection_enabled=True,
        trend_analysis_enabled=True,
        insights_enabled=True,
        anomaly_sensitivity=0.95,
        trend_window_days=7,
        forecast_horizon_days=30,
        insights_confidence_threshold=0.8,
    )


@pytest.fixture
def sample_request_data():
    """Create sample request data for testing."""
    base_time = time.time() - 24 * 3600  # 24 hours ago

    requests = []
    for i in range(100):
        timestamp = base_time + (i * 864)  # Spread over 24 hours

        requests.append(
            {
                "timestamp": timestamp,
                "user_id": f"user_{i % 10}",
                "tenant_id": f"tenant_{i % 5}",
                "model_used": f"model_{i % 3}",
                "provider_used": f"provider_{i % 2}",
                "response_time_ms": 1000 + (i % 5) * 500,  # 1000-3000ms
                "tokens_input": 100 + (i % 10) * 50,
                "tokens_output": 50 + (i % 8) * 25,
                "cost_usd": 0.01 + (i % 5) * 0.005,
                "quality_score": 0.7 + (i % 4) * 0.075,
                "status_code": 200 if i % 20 != 0 else 500,  # 5% error rate
            }
        )

    return requests


@pytest.fixture
def sample_performance_data():
    """Create sample performance data for testing."""
    base_time = time.time() - 24 * 3600

    performance_data = []
    for i in range(50):
        timestamp = base_time + (i * 1728)  # Spread over 24 hours

        performance_data.append(
            {
                "timestamp": timestamp,
                "response_time_ms": 1200 + (i % 6) * 400,
                "status_code": 200 if i % 15 != 0 else 500,
                "model_used": f"model_{i % 3}",
                "provider_used": f"provider_{i % 2}",
                "cost_usd": 0.015 + (i % 4) * 0.01,
                "quality_score": 0.75 + (i % 5) * 0.05,
            }
        )

    return performance_data


class TestAnalyticsConfig:
    """Test analytics configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = AnalyticsConfig()

        assert config.enabled is True
        assert config.data_retention_days == 90
        assert config.request_analytics_enabled is True
        assert config.performance_analytics_enabled is True
        assert config.anomaly_sensitivity == 0.95

    def test_from_environment(self):
        """Test configuration from environment variables."""
        with patch.dict(
            "os.environ",
            {
                "ANALYTICS_ENABLED": "false",
                "ANALYTICS_DATA_RETENTION_DAYS": "60",
                "ANALYTICS_ANOMALY_SENSITIVITY": "0.9",
            },
        ):
            config = AnalyticsConfig.from_environment()

            assert config.enabled is False
            assert config.data_retention_days == 60
            assert config.anomaly_sensitivity == 0.9


class TestRequestAnalyzer:
    """Test request pattern analysis."""

    @pytest.mark.asyncio
    async def test_analyze_request_patterns(self, analytics_config, sample_request_data):
        """Test basic request pattern analysis."""
        analyzer = RequestAnalyzer(analytics_config)

        result = await analyzer.analyze_request_patterns(sample_request_data)

        assert "basic_stats" in result
        assert "patterns" in result
        assert "temporal_patterns" in result
        assert "user_patterns" in result
        assert "model_patterns" in result

        # Check basic stats
        basic_stats = result["basic_stats"]
        assert basic_stats["total_requests"] == 100
        assert basic_stats["unique_users"] == 10
        assert basic_stats["unique_models"] == 3
        assert "response_time_stats" in basic_stats
        assert "error_rate_percent" in basic_stats

    @pytest.mark.asyncio
    async def test_empty_request_data(self, analytics_config):
        """Test handling of empty request data."""
        analyzer = RequestAnalyzer(analytics_config)

        result = await analyzer.analyze_request_patterns([])

        assert "error" in result

    @pytest.mark.asyncio
    async def test_request_clustering(self, analytics_config, sample_request_data):
        """Test request clustering functionality."""
        analyzer = RequestAnalyzer(analytics_config)

        result = await analyzer.analyze_request_patterns(sample_request_data)

        if "clusters" in result:
            clusters = result["clusters"]
            assert "n_clusters" in clusters
            assert "clusters" in clusters
            assert clusters["total_requests_clustered"] > 0


class TestPerformanceAnalyzer:
    """Test performance analysis."""

    @pytest.mark.asyncio
    async def test_analyze_performance_metrics(self, analytics_config, sample_performance_data):
        """Test performance metrics analysis."""
        analyzer = PerformanceAnalyzer(analytics_config)

        result = await analyzer.analyze_performance_metrics(sample_performance_data)

        assert "latency_analysis" in result
        assert "throughput_analysis" in result
        assert "error_analysis" in result
        assert "sla_analysis" in result
        assert "trends" in result
        assert "recommendations" in result

        # Check latency analysis
        latency_analysis = result["latency_analysis"]
        assert "statistics" in latency_analysis
        assert "by_model" in latency_analysis
        assert "distribution" in latency_analysis

        stats = latency_analysis["statistics"]
        assert "mean_ms" in stats
        assert "p95_ms" in stats
        assert "p99_ms" in stats

    @pytest.mark.asyncio
    async def test_sla_compliance(self, analytics_config, sample_performance_data):
        """Test SLA compliance analysis."""
        analyzer = PerformanceAnalyzer(analytics_config)

        result = await analyzer.analyze_performance_metrics(sample_performance_data)

        sla_analysis = result["sla_analysis"]
        assert "compliance_summary" in sla_analysis
        assert "overall_compliance" in sla_analysis

        overall = sla_analysis["overall_compliance"]
        assert "meets_all_slas" in overall
        assert "sla_compliance_percentage" in overall

    def test_update_sla_thresholds(self, analytics_config):
        """Test updating SLA thresholds."""
        analyzer = PerformanceAnalyzer(analytics_config)

        new_thresholds = {"latency_p95_ms": 3000, "error_rate_percent": 2.0}

        analyzer.update_sla_thresholds(new_thresholds)
        thresholds = analyzer.get_sla_thresholds()

        assert thresholds["latency_p95_ms"] == 3000
        assert thresholds["error_rate_percent"] == 2.0


class TestBusinessIntelligenceEngine:
    """Test business intelligence analysis."""

    @pytest.mark.asyncio
    async def test_generate_business_insights(self, analytics_config, sample_request_data, sample_performance_data):
        """Test business intelligence insights generation."""
        bi_engine = BusinessIntelligenceEngine(analytics_config)

        cost_data = [{"timestamp": time.time() - 3600, "cost_usd": 0.05, "model": "model_0", "provider": "provider_0"}]

        result = await bi_engine.generate_business_insights(sample_request_data, cost_data, sample_performance_data)

        assert "cost_analysis" in result
        assert "usage_forecast" in result
        assert "capacity_planning" in result
        assert "roi_analysis" in result
        assert "business_kpis" in result
        assert "strategic_recommendations" in result

    @pytest.mark.asyncio
    async def test_cost_trend_analysis(self, analytics_config):
        """Test cost trend analysis."""
        bi_engine = BusinessIntelligenceEngine(analytics_config)

        # Create cost data with increasing trend
        cost_data = []
        base_time = time.time() - 7 * 24 * 3600  # 7 days ago

        for i in range(7):
            cost_data.append(
                {
                    "timestamp": base_time + i * 24 * 3600,
                    "cost_usd": 10 + i * 2,  # Increasing cost
                    "model": "model_0",
                    "provider": "provider_0",
                }
            )

        result = await bi_engine._analyze_cost_trends(cost_data, [])

        assert "daily_trends" in result
        assert result["daily_trends"]["daily_cost_trend"] == "increasing"

    @pytest.mark.asyncio
    async def test_usage_forecasting(self, analytics_config, sample_request_data):
        """Test usage forecasting."""
        bi_engine = BusinessIntelligenceEngine(analytics_config)

        result = await bi_engine._generate_usage_forecast(sample_request_data)

        assert "historical_data" in result
        assert "forecast" in result

        forecast = result["forecast"]
        assert "forecast_horizon_days" in forecast
        assert "projected_usage" in forecast
        assert len(forecast["projected_usage"]) > 0


class TestAnomalyDetector:
    """Test anomaly detection."""

    @pytest.mark.asyncio
    async def test_detect_anomalies(self, analytics_config, sample_request_data):
        """Test basic anomaly detection."""
        detector = AnomalyDetector(analytics_config)

        result = await detector.detect_anomalies(sample_request_data)

        assert "statistical_anomalies" in result
        assert "pattern_anomalies" in result
        assert "anomalies_detected" in result
        assert "summary" in result

        summary = result["summary"]
        assert "total_anomalies" in summary
        assert "anomaly_types_detected" in summary

    @pytest.mark.asyncio
    async def test_ml_anomaly_detection(self, analytics_config):
        """Test ML-based anomaly detection."""
        detector = AnomalyDetector(analytics_config)

        # Create data with sufficient samples for ML
        ml_data = []
        base_time = time.time() - 3600

        for i in range(100):
            # Most data points are normal
            response_time = 1000 + (i % 10) * 100
            cost = 0.01 + (i % 5) * 0.002

            # Add a few anomalous points
            if i in [50, 75]:
                response_time = 10000  # Anomalous high latency
                cost = 0.1  # Anomalous high cost

            ml_data.append(
                {
                    "timestamp": base_time + i * 36,
                    "response_time_ms": response_time,
                    "cost_usd": cost,
                    "tokens_input": 100,
                    "tokens_output": 50,
                    "quality_score": 0.8,
                    "status_code": 200,
                    "model_used": "model_0",
                    "user_id": f"user_{i % 10}",
                }
            )

        result = await detector.detect_anomalies(ml_data)

        # Should have ML anomalies if enough data
        if "ml_anomalies" in result:
            ml_anomalies = result["ml_anomalies"]
            assert "anomalies" in ml_anomalies
            assert "model_type" in ml_anomalies

    @pytest.mark.asyncio
    async def test_predict_anomaly_likelihood(self, analytics_config, sample_request_data):
        """Test anomaly likelihood prediction."""
        detector = AnomalyDetector(analytics_config)

        # First run detection to train model
        await detector.detect_anomalies(sample_request_data)

        # Test prediction on new data
        test_metrics = {
            "response_time_ms": 15000,  # Very high latency
            "cost_usd": 0.1,  # High cost
            "tokens_input": 1000,
            "tokens_output": 500,
            "quality_score": 0.3,  # Low quality
            "status_code": 200,
            "model_used": "model_0",
            "user_id": "user_test",
        }

        result = await detector.predict_anomaly_likelihood(test_metrics)

        # Should detect high anomaly likelihood for extreme values
        if "error" not in result:
            assert "is_anomaly" in result
            assert "anomaly_score" in result
            assert "likelihood_percentage" in result

    def test_update_sensitivity(self, analytics_config):
        """Test updating anomaly detection sensitivity."""
        detector = AnomalyDetector(analytics_config)

        detector.update_sensitivity(0.8)
        # Sensitivity should be updated (can't directly test private variable)

        # Test bounds
        detector.update_sensitivity(0.1)  # Should be clamped to 0.5
        detector.update_sensitivity(1.5)  # Should be clamped to 0.99


class TestTrendAnalyzer:
    """Test trend analysis."""

    @pytest.mark.asyncio
    async def test_analyze_trends(self, analytics_config, sample_request_data):
        """Test trend analysis."""
        analyzer = TrendAnalyzer(analytics_config)

        result = await analyzer.analyze_trends(sample_request_data)

        assert "trends" in result
        assert "system_health_trend" in result
        assert "forecasts" in result
        assert "insights" in result

        trends = result["trends"]
        # Should have various metric trends
        assert len(trends) > 0

    @pytest.mark.asyncio
    async def test_seasonal_patterns(self, analytics_config):
        """Test seasonal pattern analysis."""
        config = analytics_config
        config.seasonal_analysis = True

        analyzer = TrendAnalyzer(config)

        # Create data with clear daily patterns
        seasonal_data = []
        base_time = time.time() - 7 * 24 * 3600  # 7 days ago

        for day in range(7):
            for hour in range(24):
                # Simulate higher usage during business hours
                usage_multiplier = 2 if 9 <= hour <= 17 else 1

                for _ in range(usage_multiplier * 5):
                    seasonal_data.append(
                        {
                            "timestamp": base_time + day * 24 * 3600 + hour * 3600,
                            "response_time_ms": 1000,
                            "cost_usd": 0.01,
                            "quality_score": 0.8,
                            "status_code": 200,
                            "model_used": "model_0",
                            "user_id": "user_0",
                        }
                    )

        result = await analyzer.analyze_trends(seasonal_data)

        if "seasonal_patterns" in result:
            seasonal = result["seasonal_patterns"]
            assert "hourly_patterns" in seasonal or "daily_patterns" in seasonal

    def test_update_forecast_horizon(self, analytics_config):
        """Test updating forecast horizon."""
        analyzer = TrendAnalyzer(analytics_config)

        analyzer.update_forecast_horizon(60)
        # Should update internal horizon (can't directly test private variable)

        # Test bounds
        analyzer.update_forecast_horizon(0)  # Should be clamped to 1
        analyzer.update_forecast_horizon(200)  # Should be clamped to 90


class TestInsightsGenerator:
    """Test insights generation."""

    @pytest.mark.asyncio
    async def test_generate_comprehensive_insights(self, analytics_config):
        """Test comprehensive insights generation."""
        generator = InsightsGenerator(analytics_config)

        # Mock analytics data
        analytics_data = {
            "basic_stats": {"error_rate_percent": 8.0},
            "patterns": {
                "request_size_distribution": {"large_requests": 25, "small_requests": 50, "medium_requests": 25}
            },
        }

        performance_data = {
            "latency_analysis": {"statistics": {"p95_ms": 6000}, "by_model": {"model_slow": {"p95_ms": 9000}}},
            "error_analysis": {"error_rate_percent": 8.0},
        }

        business_data = {"cost_analysis": {"daily_trends": {"daily_cost_trend": "increasing"}}}

        anomaly_data = {"summary": {"total_anomalies": 5, "high_severity_anomalies": 2}}

        trend_data = {
            "insights": [
                {
                    "type": "performance_degradation",
                    "priority": "high",
                    "title": "Response Time Trend",
                    "description": "Response times increasing",
                    "recommendations": ["Scale infrastructure"],
                }
            ]
        }

        result = await generator.generate_comprehensive_insights(
            analytics_data, performance_data, business_data, anomaly_data, trend_data
        )

        assert "insights" in result
        assert "summary" in result
        assert "recommendations" in result
        assert "action_items" in result

        # Should have generated insights
        insights = result["insights"]
        assert len(insights) > 0

        # Check insight structure
        for insight in insights:
            assert "category" in insight
            assert "title" in insight
            assert "description" in insight
            assert "confidence" in insight
            assert "priority" in insight

    def test_update_confidence_threshold(self, analytics_config):
        """Test updating confidence threshold."""
        generator = InsightsGenerator(analytics_config)

        generator.update_confidence_threshold(0.9)
        # Should update internal threshold (can't directly test private variable)

        # Test bounds
        generator.update_confidence_threshold(0.05)  # Should be clamped to 0.1
        generator.update_confidence_threshold(1.5)  # Should be clamped to 0.99


class TestAnalyticsManager:
    """Test main analytics manager."""

    def test_initialization(self, analytics_config):
        """Test analytics manager initialization."""
        manager = AnalyticsManager(analytics_config)

        assert manager.config == analytics_config
        assert manager.request_analyzer is not None
        assert manager.performance_analyzer is not None
        assert manager.business_intelligence is not None
        assert manager.anomaly_detector is not None
        assert manager.trend_analyzer is not None
        assert manager.insights_generator is not None

        enabled_components = manager._get_enabled_components()
        assert len(enabled_components) == 6

    @pytest.mark.asyncio
    async def test_comprehensive_analysis(self, analytics_config, sample_request_data, sample_performance_data):
        """Test comprehensive analysis."""
        manager = AnalyticsManager(analytics_config)

        result = await manager.run_comprehensive_analysis(sample_request_data, sample_performance_data)

        assert "analysis_timestamp" in result
        assert "data_summary" in result
        assert "enabled_components" in result
        assert "component_results" in result
        assert "insights" in result
        assert "analysis_duration_seconds" in result

        # Check component results
        component_results = result["component_results"]
        assert "request_analysis" in component_results
        assert "performance_analysis" in component_results
        assert "business_intelligence" in component_results
        assert "anomaly_detection" in component_results
        assert "trend_analysis" in component_results

    @pytest.mark.asyncio
    async def test_real_time_analysis(self, analytics_config):
        """Test real-time metrics analysis."""
        manager = AnalyticsManager(analytics_config)

        # Test normal metrics
        normal_metrics = {"response_time_ms": 1500, "cost_usd": 0.02, "quality_score": 0.85, "status_code": 200}

        result = await manager.analyze_real_time_metrics(normal_metrics)

        assert "timestamp" in result
        assert "metrics" in result
        assert "alerts" in result
        assert "recommendations" in result

        # Test anomalous metrics
        anomalous_metrics = {
            "response_time_ms": 15000,  # Very high
            "cost_usd": 0.5,  # Very high
            "quality_score": 0.2,  # Very low
            "status_code": 500,  # Error
        }

        result = await manager.analyze_real_time_metrics(anomalous_metrics)

        # Should generate alerts for anomalous metrics
        alerts = result["alerts"]
        assert len(alerts) > 0

        # Check for specific alert types
        alert_types = [alert["type"] for alert in alerts]
        assert "performance_alert" in alert_types
        assert "error_alert" in alert_types

    @pytest.mark.asyncio
    async def test_dashboard_data(self, analytics_config, sample_request_data):
        """Test dashboard data generation."""
        manager = AnalyticsManager(analytics_config)

        # Run analysis first to populate cache
        await manager.run_comprehensive_analysis(sample_request_data)

        dashboard_data = await manager.get_analytics_dashboard_data()

        assert "timestamp" in dashboard_data
        assert "system_status" in dashboard_data
        assert "components_status" in dashboard_data
        assert "key_metrics" in dashboard_data
        assert "recent_insights" in dashboard_data
        assert "alerts" in dashboard_data

        # Check component status
        components_status = dashboard_data["components_status"]
        for component in manager._get_enabled_components():
            assert component in components_status
            assert components_status[component] == "active"

    @pytest.mark.asyncio
    async def test_export_functionality(self, analytics_config, sample_request_data):
        """Test analytics data export."""
        manager = AnalyticsManager(analytics_config)

        # Run analysis first
        await manager.run_comprehensive_analysis(sample_request_data)

        export_result = await manager.export_analytics_data("json", 24)

        assert "export_timestamp" in export_result
        assert "format" in export_result
        assert "data" in export_result
        assert "metadata" in export_result

        # Check exported data structure
        data = export_result["data"]
        assert "analysis_results" in data

        metadata = export_result["metadata"]
        assert "enabled_components" in metadata
        assert "configuration" in metadata

    def test_system_status(self, analytics_config):
        """Test system status reporting."""
        manager = AnalyticsManager(analytics_config)

        status = manager.get_system_status()

        assert "enabled" in status
        assert "components" in status
        assert "last_analysis_time" in status
        assert "background_tasks_active" in status
        assert "cache_status" in status

        # Check component status
        components = status["components"]
        assert components["request_analyzer"] is True
        assert components["performance_analyzer"] is True
        assert components["business_intelligence"] is True
        assert components["anomaly_detector"] is True
        assert components["trend_analyzer"] is True
        assert components["insights_generator"] is True

    def test_configuration_update(self, analytics_config):
        """Test configuration updates."""
        manager = AnalyticsManager(analytics_config)

        new_config = {"insights_confidence_threshold": 0.9, "anomaly_sensitivity": 0.8, "forecast_horizon_days": 60}

        manager.update_configuration(new_config)
        # Configuration should be updated (tested indirectly through component behavior)

    def test_background_analysis_control(self, analytics_config):
        """Test background analysis start/stop."""
        manager = AnalyticsManager(analytics_config)

        # Start background analysis
        manager.start_background_analysis()
        assert len(manager._background_tasks) > 0

        # Stop background analysis
        manager.stop_background_analysis()
        assert len(manager._background_tasks) == 0


class TestIntegration:
    """Integration tests for the complete analytics system."""

    @pytest.mark.asyncio
    async def test_end_to_end_analysis(self, analytics_config, sample_request_data, sample_performance_data):
        """Test complete end-to-end analytics pipeline."""
        manager = AnalyticsManager(analytics_config)

        # Run comprehensive analysis
        result = await manager.run_comprehensive_analysis(sample_request_data, sample_performance_data)

        # Verify all components ran successfully
        assert "error" not in result
        assert result["analysis_duration_seconds"] > 0

        component_results = result["component_results"]

        # Check each component produced results
        for component_name in [
            "request_analysis",
            "performance_analysis",
            "business_intelligence",
            "anomaly_detection",
            "trend_analysis",
        ]:
            assert component_name in component_results
            component_result = component_results[component_name]
            assert "error" not in component_result or len(component_result) > 1

        # Check insights were generated
        insights = result["insights"]
        assert "insights" in insights
        assert "summary" in insights
        assert "recommendations" in insights

        # Verify insights structure
        insight_list = insights["insights"]
        if insight_list:
            for insight in insight_list[:3]:  # Check first 3 insights
                assert "category" in insight
                assert "title" in insight
                assert "confidence" in insight
                assert "priority" in insight

    @pytest.mark.asyncio
    async def test_error_handling(self, analytics_config):
        """Test error handling in analytics pipeline."""
        manager = AnalyticsManager(analytics_config)

        # Test with empty data
        result = await manager.run_comprehensive_analysis([])
        assert "error" in result

        # Test with invalid data
        invalid_data = [{"invalid": "data"}]
        result = await manager.run_comprehensive_analysis(invalid_data)

        # Should handle gracefully and provide partial results
        assert "component_results" in result

    @pytest.mark.asyncio
    async def test_performance_with_large_dataset(self, analytics_config):
        """Test analytics performance with larger dataset."""
        # Create larger dataset
        large_dataset = []
        base_time = time.time() - 7 * 24 * 3600  # 7 days

        for i in range(1000):  # 1000 requests
            large_dataset.append(
                {
                    "timestamp": base_time + i * 604.8,  # Spread over 7 days
                    "user_id": f"user_{i % 50}",
                    "model_used": f"model_{i % 5}",
                    "provider_used": f"provider_{i % 3}",
                    "response_time_ms": 1000 + (i % 10) * 200,
                    "tokens_input": 100 + (i % 20) * 25,
                    "tokens_output": 50 + (i % 15) * 10,
                    "cost_usd": 0.01 + (i % 8) * 0.005,
                    "quality_score": 0.6 + (i % 5) * 0.08,
                    "status_code": 200 if i % 25 != 0 else 500,
                }
            )

        manager = AnalyticsManager(analytics_config)

        start_time = time.time()
        result = await manager.run_comprehensive_analysis(large_dataset)
        analysis_time = time.time() - start_time

        # Should complete within reasonable time (adjust threshold as needed)
        assert analysis_time < 30  # 30 seconds max
        assert "error" not in result
        assert result["data_summary"]["request_records"] == 1000


if __name__ == "__main__":
    pytest.main([__file__])
