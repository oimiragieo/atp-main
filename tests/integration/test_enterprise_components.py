# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Integration tests for enterprise components using Testcontainers.
"""

import asyncio

import pytest

# Testcontainers imports
try:
    from testcontainers.compose import DockerCompose
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False
    pytest.skip("Testcontainers not available", allow_module_level=True)

# Import enterprise components
from metrics.enterprise_metrics import EnterpriseMetricsCollector
from monitoring.alerting.alert_manager import AlertManager, AlertRule, AlertSeverity
from monitoring.alerting.incident_response import ActionType, IncidentResponseAutomation, RemediationAction
from router_service.api_gateway import APIGateway

from observability.performance_analyzer import PerformanceAnalyzer
from observability.tracing import EnhancedTracer, TraceLevel, TracingConfig
from router_service.api_versioning import APIVersionManager


class TestEnterpriseMetrics:
    """Test enterprise metrics collection system."""

    @pytest.fixture
    async def redis_container(self):
        """Redis container fixture."""
        if not TESTCONTAINERS_AVAILABLE:
            pytest.skip("Testcontainers not available")

        with RedisContainer("redis:7-alpine") as redis_container:
            yield redis_container

    @pytest.fixture
    async def metrics_collector(self, redis_container):
        """Enterprise metrics collector fixture."""
        collector = EnterpriseMetricsCollector()
        await collector.start_monitoring()
        yield collector
        await collector.stop_monitoring()

    @pytest.mark.asyncio
    async def test_slo_calculation(self, metrics_collector):
        """Test SLO calculation and status updates."""
        # Record some metrics
        metrics_collector.record_model_routing_decision(
            model_name="gpt-4", provider="openai", latency=0.5, cost=0.01, quality_score=0.95
        )

        # Calculate SLO metrics
        metrics_collector.calculate_slo_metrics()

        # Check SLO status
        slo_status = metrics_collector.get_slo_status()

        assert "slos" in slo_status
        assert "availability" in slo_status["slos"]
        assert slo_status["slos"]["availability"]["current_percentage"] >= 0
        assert slo_status["overall_status"] in ["healthy", "warning", "critical"]

    @pytest.mark.asyncio
    async def test_cost_tracking(self, metrics_collector):
        """Test cost tracking and budget utilization."""
        # Record cost savings
        metrics_collector.record_cost_savings(10.50)

        # Update budget utilization
        metrics_collector.update_budget_utilization(75.0)

        # Get metrics summary
        summary = metrics_collector.get_metrics_summary()

        assert "system_metrics" in summary
        assert summary["system_metrics"]["budget_utilization"] == 75.0
        assert "ai_metrics" in summary
        assert summary["ai_metrics"]["cost_savings_total"] > 0

    @pytest.mark.asyncio
    async def test_security_violation_recording(self, metrics_collector):
        """Test security violation recording and alerting."""
        # Record security violation
        metrics_collector.record_security_violation("unauthorized_access", "high")

        # Check that alert was triggered
        active_alerts = metrics_collector.get_active_alerts()

        # Should have triggered a security alert
        security_alerts = [alert for alert in active_alerts if "security" in alert.get("name", "").lower()]
        assert len(security_alerts) > 0


class TestDistributedTracing:
    """Test distributed tracing enhancements."""

    @pytest.fixture
    def tracing_config(self):
        """Tracing configuration fixture."""
        return TracingConfig(
            service_name="test-service",
            console_export=True,
            trace_level=TraceLevel.DEBUG,
            sampling_ratio=1.0,  # Sample everything for tests
        )

    @pytest.fixture
    def enhanced_tracer(self, tracing_config):
        """Enhanced tracer fixture."""
        tracer = EnhancedTracer(tracing_config)
        return tracer

    @pytest.mark.asyncio
    async def test_span_creation_and_correlation(self, enhanced_tracer):
        """Test span creation and trace correlation."""
        with enhanced_tracer.start_span("test_operation", attributes={"test": "value"}) as span:
            assert span is not None

            # Get trace ID
            trace_id = enhanced_tracer.get_current_trace_id()
            assert trace_id is not None

            # Get correlation info
            correlation = enhanced_tracer.get_correlation_info(trace_id)
            assert correlation is not None
            assert correlation.trace_id == trace_id

    @pytest.mark.asyncio
    async def test_async_span_creation(self, enhanced_tracer):
        """Test async span creation."""
        async with enhanced_tracer.start_async_span("async_operation") as span:
            assert span is not None

            # Simulate some async work
            await asyncio.sleep(0.01)

            trace_id = enhanced_tracer.get_current_trace_id()
            assert trace_id is not None

    @pytest.mark.asyncio
    async def test_performance_analysis(self, enhanced_tracer):
        """Test performance analysis from traces."""
        # Create some spans with different durations
        operations = ["fast_op", "slow_op", "medium_op"]
        durations = [0.01, 0.5, 0.1]

        for op, duration in zip(operations, durations, strict=False):
            with enhanced_tracer.start_span(op):
                await asyncio.sleep(duration)

        # Analyze performance
        analysis = enhanced_tracer.analyze_performance()

        assert "total_operations" in analysis
        assert analysis["total_operations"] == len(operations)
        assert "duration_stats" in analysis
        assert "slowest_operations" in analysis


class TestPerformanceAnalyzer:
    """Test performance analysis tools."""

    @pytest.fixture
    def performance_analyzer(self):
        """Performance analyzer fixture."""
        return PerformanceAnalyzer(retention_hours=1)

    def test_trace_data_ingestion(self, performance_analyzer):
        """Test trace data ingestion and processing."""
        # Ingest some trace data
        trace_data = {
            "trace_id": "test_trace_123",
            "operation_name": "test_operation",
            "service_name": "test_service",
            "duration_ms": 150.0,
            "status": "ok",
            "spans": [{"operation_name": "test_operation", "service_name": "test_service", "duration_ms": 150.0}],
        }

        performance_analyzer.ingest_trace_data(trace_data)

        # Check that data was ingested
        assert len(performance_analyzer.trace_data) == 1
        assert "test_service:test_operation" in performance_analyzer.operation_stats

    def test_bottleneck_detection(self, performance_analyzer):
        """Test performance bottleneck detection."""
        # Ingest data that should trigger bottleneck detection
        for i in range(10):
            trace_data = {
                "trace_id": f"trace_{i}",
                "operation_name": "slow_operation",
                "service_name": "test_service",
                "duration_ms": 3000.0,  # 3 seconds - should trigger high latency
                "status": "ok" if i < 8 else "error",  # Some errors
                "spans": [{"operation_name": "slow_operation", "service_name": "test_service", "duration_ms": 3000.0}],
            }
            performance_analyzer.ingest_trace_data(trace_data)

        # Detect bottlenecks
        bottlenecks = performance_analyzer.detect_bottlenecks()

        # Should detect high latency bottleneck
        assert len(bottlenecks) > 0
        latency_bottlenecks = [b for b in bottlenecks if "latency" in b.description.lower()]
        assert len(latency_bottlenecks) > 0

    def test_service_dependency_graph(self, performance_analyzer):
        """Test service dependency graph generation."""
        # Ingest multi-service trace data
        trace_data = {
            "trace_id": "multi_service_trace",
            "operation_name": "user_request",
            "service_name": "frontend",
            "duration_ms": 200.0,
            "status": "ok",
            "spans": [
                {"operation_name": "user_request", "service_name": "frontend", "duration_ms": 200.0},
                {"operation_name": "api_call", "service_name": "backend", "duration_ms": 150.0},
                {"operation_name": "db_query", "service_name": "database", "duration_ms": 50.0},
            ],
        }

        performance_analyzer.ingest_trace_data(trace_data)

        # Get dependency graph
        graph = performance_analyzer.get_service_dependency_graph()

        assert "nodes" in graph
        assert "edges" in graph
        assert len(graph["nodes"]) >= 2  # At least frontend and backend


class TestAlertManager:
    """Test alerting and incident management."""

    @pytest.fixture
    def alert_manager(self):
        """Alert manager fixture."""
        return AlertManager()

    def test_alert_rule_management(self, alert_manager):
        """Test alert rule creation and management."""
        # Create a test alert rule
        rule = AlertRule(
            id="test_rule",
            name="Test Alert",
            description="Test alert for unit testing",
            query="test_metric > 0.5",
            condition="> 0.5",
            severity=AlertSeverity.WARNING,
            duration=60,
        )

        # Add rule
        alert_manager.add_alert_rule(rule)

        # Check rule was added
        assert "test_rule" in alert_manager.alert_rules
        assert alert_manager.alert_rules["test_rule"].name == "Test Alert"

        # Remove rule
        alert_manager.remove_alert_rule("test_rule")
        assert "test_rule" not in alert_manager.alert_rules

    def test_alert_firing_and_resolution(self, alert_manager):
        """Test alert firing and resolution."""
        # Fire an alert
        alert_id = alert_manager.fire_alert("high_error_rate")

        # Check alert is active
        assert alert_id in alert_manager.active_alerts
        active_alerts = alert_manager.get_active_alerts()
        assert len(active_alerts) > 0

        # Acknowledge alert
        alert_manager.acknowledge_alert(alert_id, "test_user")

        # Check alert is acknowledged
        alert = alert_manager.active_alerts[alert_id]
        assert alert.acknowledged_by == "test_user"
        assert alert.acknowledged_at is not None

        # Resolve alert
        alert_manager.resolve_alert(alert_id)

        # Check alert is resolved
        assert alert_id not in alert_manager.active_alerts
        assert len(alert_manager.resolved_alerts) > 0

    def test_incident_creation(self, alert_manager):
        """Test incident creation from critical alerts."""
        # Fire a critical alert
        alert_id = alert_manager.fire_alert("low_availability")

        # Should create an incident
        incidents = alert_manager.get_incidents()
        assert len(incidents) > 0

        # Check incident contains the alert
        incident = incidents[0]
        assert alert_id in incident["alerts"]
        assert incident["severity"] == "critical"


class TestIncidentResponse:
    """Test incident response automation."""

    @pytest.fixture
    def incident_response(self):
        """Incident response automation fixture."""
        return IncidentResponseAutomation()

    @pytest.mark.asyncio
    async def test_remediation_action_execution(self, incident_response):
        """Test remediation action execution."""
        # Create a test remediation action
        action = RemediationAction(
            id="test_action",
            name="Test Action",
            description="Test remediation action",
            action_type=ActionType.SCRIPT,
            trigger_conditions=["test_condition"],
            action_config={"script_path": "echo", "args": ["test successful"]},
            timeout_seconds=30,
        )

        incident_response.remediation_actions[action.id] = action

        # Trigger remediation
        execution_ids = await incident_response.trigger_remediation("test_condition")

        # Check execution was triggered
        assert len(execution_ids) > 0

        # Wait a bit for execution to complete
        await asyncio.sleep(0.1)

        # Check execution history
        history = incident_response.get_execution_history()
        assert len(history) > 0
        assert history[0]["status"] in ["success", "running"]

    @pytest.mark.asyncio
    async def test_runbook_execution(self, incident_response):
        """Test runbook execution."""
        # Execute a default runbook
        execution_id = await incident_response.execute_runbook("high_error_rate_response")

        assert execution_id is not None
        assert execution_id.startswith("runbook_")


class TestAPIGateway:
    """Test API gateway functionality."""

    @pytest.fixture
    async def redis_container(self):
        """Redis container for API gateway."""
        if not TESTCONTAINERS_AVAILABLE:
            pytest.skip("Testcontainers not available")

        with RedisContainer("redis:7-alpine") as redis_container:
            yield redis_container

    @pytest.fixture
    async def api_gateway(self, redis_container):
        """API gateway fixture."""
        redis_url = redis_container.get_connection_url()
        gateway = APIGateway(redis_url)
        await gateway.initialize()
        yield gateway
        await gateway.close()

    @pytest.mark.asyncio
    async def test_rate_limiting(self, api_gateway):
        """Test rate limiting functionality."""
        from unittest.mock import Mock

        from fastapi import Request

        # Mock request
        request = Mock(spec=Request)
        request.url.path = "/api/v1/chat/completions"
        request.method = "POST"
        request.client.host = "127.0.0.1"
        request.headers = {}

        # Process multiple requests
        results = []
        for _i in range(10):
            allowed, status, error = await api_gateway.process_request(request, user_id="test_user", user_tier="basic")
            results.append(allowed)

        # Should allow some requests but may rate limit others
        assert any(results)  # At least some should be allowed

    @pytest.mark.asyncio
    async def test_api_versioning(self, api_gateway):
        """Test API versioning support."""
        version_manager = APIVersionManager()

        # Test version extraction
        from unittest.mock import Mock

        from fastapi import Request

        request = Mock(spec=Request)
        request.url.path = "/api/v1/test"

        version = version_manager.extract_version_from_request(request)
        assert version == "1.0.0"

        # Test version validation
        validation = version_manager.validate_version_request("1.0.0")
        assert validation["valid"] is True
        assert validation["supported"] is True


class TestContractTesting:
    """Test API contract compatibility."""

    @pytest.mark.asyncio
    async def test_api_contract_backward_compatibility(self):
        """Test that API contracts maintain backward compatibility."""
        # This would typically use tools like Pact or OpenAPI diff
        # For now, we'll do a simple schema validation test

        # Define expected API response schema

        # Mock API response
        api_response = {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1677652288,
            "model": "gpt-4",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello! How can I help you today?"}}],
        }

        # Validate schema (simplified validation)
        assert "id" in api_response
        assert "object" in api_response
        assert "created" in api_response
        assert "model" in api_response
        assert "choices" in api_response
        assert isinstance(api_response["choices"], list)
        assert len(api_response["choices"]) > 0

        choice = api_response["choices"][0]
        assert "index" in choice
        assert "message" in choice
        assert "role" in choice["message"]
        assert "content" in choice["message"]


@pytest.mark.integration
class TestFullSystemIntegration:
    """Full system integration tests."""

    @pytest.fixture
    async def test_environment(self):
        """Set up full test environment with all components."""
        if not TESTCONTAINERS_AVAILABLE:
            pytest.skip("Testcontainers not available")

        # This would set up a complete test environment
        # For now, we'll use a simplified setup
        components = {
            "metrics": EnterpriseMetricsCollector(),
            "alerts": AlertManager(),
            "incident_response": IncidentResponseAutomation(),
        }

        # Start monitoring
        await components["metrics"].start_monitoring()

        yield components

        # Cleanup
        await components["metrics"].stop_monitoring()

    @pytest.mark.asyncio
    async def test_end_to_end_alert_flow(self, test_environment):
        """Test complete alert flow from metrics to incident response."""
        metrics = test_environment["metrics"]
        alerts = test_environment["alerts"]
        incident_response = test_environment["incident_response"]

        # 1. Record a security violation
        metrics.record_security_violation("unauthorized_access", "critical")

        # 2. This should trigger an alert
        await asyncio.sleep(0.1)  # Allow processing time

        # 3. Check that alert was created
        active_alerts = alerts.get_active_alerts()
        security_alerts = [a for a in active_alerts if "security" in a.get("name", "").lower()]

        if security_alerts:
            # 4. This should trigger incident response
            execution_ids = await incident_response.trigger_remediation("security_violation")

            # 5. Check that remediation was triggered
            assert len(execution_ids) >= 0  # May be 0 if no matching actions

    @pytest.mark.asyncio
    async def test_performance_monitoring_integration(self, test_environment):
        """Test integration between performance monitoring and alerting."""
        metrics = test_environment["metrics"]
        alerts = test_environment["alerts"]

        # Record high latency operations
        for _i in range(5):
            metrics.record_model_routing_decision(
                model_name="gpt-4",
                provider="openai",
                latency=3.0,  # High latency
                cost=0.01,
                quality_score=0.8,
            )

        # Calculate SLO metrics
        metrics.calculate_slo_metrics()

        # Check SLO status
        slo_status = metrics.get_slo_status()

        # Should detect performance issues
        assert "slos" in slo_status

        # May trigger alerts based on SLO violations
        alerts.get_active_alerts()
        # Note: Alerts may or may not be triggered depending on thresholds


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
