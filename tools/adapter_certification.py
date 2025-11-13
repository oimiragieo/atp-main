#!/usr/bin/env python3
"""Adapter Certification Testing Suite."""

import asyncio
import statistics
import time
from dataclasses import dataclass
from typing import Any

import adapter_pb2
import adapter_pb2_grpc
import grpc
from adapter_metrics import get_metrics_collector


@dataclass
class CertificationResult:
    adapter_name: str
    level: int
    passed: bool
    score: float
    issues: list[str]
    metrics: dict[str, Any]
    recommendations: list[str]


class AdapterCertificationSuite:
    """Comprehensive adapter certification testing."""

    def __init__(self, adapter_host: str = "localhost", adapter_port: int = 50051):
        self.adapter_host = adapter_host
        self.adapter_port = adapter_port
        self.channel = None
        self.stub = None

    def connect(self) -> bool:
        """Establish connection to adapter service."""
        try:
            self.channel = grpc.insecure_channel(f"{self.adapter_host}:{self.adapter_port}")
            self.stub = adapter_pb2_grpc.AdapterServiceStub(self.channel)
            return True
        except Exception as e:
            print(f"Failed to connect to adapter: {e}")
            return False

    def disconnect(self):
        """Close connection to adapter service."""
        if self.channel:
            self.channel.close()

    async def run_certification(self, adapter_name: str) -> CertificationResult:
        """Run complete certification suite."""
        print(f"Starting certification for {adapter_name}")

        issues = []
        metrics = {}
        recommendations = []

        # Test 1: Basic connectivity
        if not self.connect():
            return CertificationResult(
                adapter_name=adapter_name,
                level=0,
                passed=False,
                score=0.0,
                issues=["Cannot connect to adapter service"],
                metrics={},
                recommendations=["Ensure adapter service is running and accessible"],
            )

        # Test 2: Health check
        health_ok = await self._test_health_check()
        if not health_ok:
            issues.append("Health check failed")
            recommendations.append("Implement proper health check endpoint")

        # Test 3: Estimate functionality
        estimate_metrics = await self._test_estimate_functionality()
        metrics.update(estimate_metrics)

        if estimate_metrics.get("estimate_error_rate", 1.0) > 0.05:
            issues.append("Estimate error rate too high")
            recommendations.append("Improve error handling in Estimate method")

        if estimate_metrics.get("estimate_p95_ms", float("inf")) > 500:
            issues.append("Estimate response time too slow")
            recommendations.append("Optimize Estimate method performance")

        # Test 4: Stream functionality
        stream_metrics = await self._test_stream_functionality()
        metrics.update(stream_metrics)

        if stream_metrics.get("stream_error_rate", 1.0) > 0.05:
            issues.append("Stream error rate too high")
            recommendations.append("Improve error handling in Stream method")

        if stream_metrics.get("stream_p95_ms", float("inf")) > 2000:
            issues.append("Stream response time too slow")
            recommendations.append("Optimize Stream method performance")

        # Test 5: Load testing
        load_metrics = await self._test_load_handling()
        metrics.update(load_metrics)

        if load_metrics.get("load_error_rate", 1.0) > 0.01:
            issues.append("Poor performance under load")
            recommendations.append("Implement request queuing and rate limiting")

        # Test 6: Token estimation accuracy
        accuracy_metrics = await self._test_token_accuracy()
        metrics.update(accuracy_metrics)

        if accuracy_metrics.get("token_accuracy", 0.0) < 0.95:
            issues.append("Token estimation accuracy too low")
            recommendations.append("Improve token counting algorithm")

        # Calculate certification level and score
        level, score = self._calculate_certification_level(metrics, issues)

        self.disconnect()

        return CertificationResult(
            adapter_name=adapter_name,
            level=level,
            passed=len(issues) == 0,
            score=score,
            issues=issues,
            metrics=metrics,
            recommendations=recommendations,
        )

    async def _test_health_check(self) -> bool:
        """Test health check functionality."""
        try:
            request = adapter_pb2.HealthRequest()
            response = self.stub.Health(request)
            return response.p95_ms > 0 and response.error_rate >= 0
        except Exception:
            return False

    async def _test_estimate_functionality(self) -> dict[str, Any]:
        """Test estimate functionality with timing and error tracking."""
        response_times = []
        errors = 0
        total_requests = 100

        test_prompts = [
            '{"messages": [{"role": "user", "content": "Hello"}]}',
            '{"messages": [{"role": "user", "content": "Write a short story"}]}',
            '{"messages": [{"role": "user", "content": "Explain quantum computing"}]}',
        ]

        for i in range(total_requests):
            try:
                start_time = time.time()
                request = adapter_pb2.EstimateRequest(
                    stream_id=f"test-{i}", task_type="chat_completion", prompt_json=test_prompts[i % len(test_prompts)]
                )
                response = self.stub.Estimate(request)
                end_time = time.time()

                response_times.append((end_time - start_time) * 1000)

                # Validate response
                if response.in_tokens == 0 or response.confidence < 0:
                    errors += 1

            except Exception:
                errors += 1

        return {
            "estimate_requests_total": total_requests,
            "estimate_errors_total": errors,
            "estimate_error_rate": errors / total_requests,
            "estimate_p95_ms": statistics.quantiles(response_times, n=20)[18] if response_times else float("inf"),
            "estimate_avg_ms": statistics.mean(response_times) if response_times else float("inf"),
        }

    async def _test_stream_functionality(self) -> dict[str, Any]:
        """Test stream functionality."""
        response_times = []
        errors = 0
        total_requests = 50

        for i in range(total_requests):
            try:
                start_time = time.time()
                request = adapter_pb2.StreamRequest(
                    stream_id=f"stream-test-{i}",
                    prompt_json='{"messages": [{"role": "user", "content": "Tell me a joke"}]}',
                )

                chunks = []
                for chunk in self.stub.Stream(request):
                    chunks.append(chunk)

                end_time = time.time()
                response_times.append((end_time - start_time) * 1000)

                if not chunks:
                    errors += 1

            except Exception:
                errors += 1

        return {
            "stream_requests_total": total_requests,
            "stream_errors_total": errors,
            "stream_error_rate": errors / total_requests,
            "stream_p95_ms": statistics.quantiles(response_times, n=20)[18] if response_times else float("inf"),
            "stream_avg_ms": statistics.mean(response_times) if response_times else float("inf"),
        }

    async def _test_load_handling(self) -> dict[str, Any]:
        """Test adapter performance under load."""
        concurrent_requests = 50
        response_times = []
        errors = 0

        async def single_request(req_id: int):
            try:
                start_time = time.time()
                request = adapter_pb2.EstimateRequest(
                    stream_id=f"load-test-{req_id}",
                    task_type="chat_completion",
                    prompt_json='{"messages": [{"role": "user", "content": "Hello"}]}',
                )
                self.stub.Estimate(request)
                end_time = time.time()

                response_times.append((end_time - start_time) * 1000)
                return True
            except Exception:
                nonlocal errors
                errors += 1
                return False

        # Run concurrent requests
        tasks = [single_request(i) for i in range(concurrent_requests)]
        await asyncio.gather(*tasks)

        return {
            "load_concurrent_requests": concurrent_requests,
            "load_errors_total": errors,
            "load_error_rate": errors / concurrent_requests,
            "load_p95_ms": statistics.quantiles(response_times, n=20)[18] if response_times else float("inf"),
            "load_avg_ms": statistics.mean(response_times) if response_times else float("inf"),
        }

    async def _test_token_accuracy(self) -> dict[str, Any]:
        """Test token estimation accuracy."""
        test_cases = [
            ("Hello", 1),
            ("Hello world", 2),
            ("This is a longer message with more words", 8),
            ("A very long message with many many words that should test token counting accuracy", 15),
        ]

        total_accuracy = 0
        for prompt, expected_tokens in test_cases:
            try:
                request = adapter_pb2.EstimateRequest(
                    stream_id="accuracy-test",
                    task_type="chat_completion",
                    prompt_json=f'{{"messages": [{{"role": "user", "content": "{prompt}"}}]}}',
                )
                response = self.stub.Estimate(request)

                # Simple accuracy check (within 50% of expected)
                if expected_tokens * 0.5 <= response.in_tokens <= expected_tokens * 1.5:
                    total_accuracy += 1

            except Exception as e:
                # Log the error but continue with accuracy testing
                print(f"Token accuracy test failed: {e}")

        return {"token_accuracy_tests": len(test_cases), "token_accuracy_score": total_accuracy / len(test_cases)}

    def _calculate_certification_level(self, metrics: dict[str, Any], issues: list[str]) -> tuple[int, float]:
        """Calculate certification level and score."""
        score = 100.0

        # Deduct points for issues
        score -= len(issues) * 10

        # Performance deductions
        if metrics.get("estimate_p95_ms", float("inf")) > 500:
            score -= 15
        if metrics.get("stream_p95_ms", float("inf")) > 2000:
            score -= 15
        if metrics.get("load_error_rate", 1.0) > 0.01:
            score -= 20
        if metrics.get("token_accuracy_score", 0.0) < 0.95:
            score -= 10

        # Determine level
        if score >= 90 and len(issues) == 0:
            level = 2  # Performance certification
        elif score >= 75:
            level = 1  # Basic certification
        else:
            level = 0  # Not certified

        return level, max(0.0, score)


async def main():
    """Run certification suite."""
    suite = AdapterCertificationSuite()
    metrics_collector = get_metrics_collector()

    # Test with available adapters
    adapters_to_test = ["ollama_adapter", "persona_adapter"]

    for adapter_name in adapters_to_test:
        print(f"\n{'=' * 50}")
        print(f"Testing {adapter_name}")
        print("=" * 50)

        result = await suite.run_certification(adapter_name)

        # Record certification result in metrics
        metrics_collector.update_certification_result(adapter_name, result.level, result.score)

        # Update health status based on whether basic connectivity worked
        health_status = len(result.issues) == 0 or "Cannot connect" not in str(result.issues)
        metrics_collector.update_health_status(adapter_name, health_status)

        print("\nCertification Results:")
        print(f"  Level: {result.level}")
        print(f"  Passed: {result.passed}")
        print(f"  Score: {result.score:.1f}%")

        if result.issues:
            print("\nIssues:")
            for issue in result.issues:
                print(f"  - {issue}")

        if result.recommendations:
            print("\nRecommendations:")
            for rec in result.recommendations:
                print(f"  - {rec}")

        print("\nKey Metrics:")
        for key, value in result.metrics.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.3f}")
            else:
                print(f"  {key}: {value}")

    # Update Prometheus metrics
    metrics_collector.update_prometheus_metrics()

    # Save final metrics
    metrics_collector.save_metrics_to_file("certification_results.json")
    print(f"\n{'=' * 50}")
    print("Certification Summary")
    print("=" * 50)
    print("Results saved to certification_results.json")

    # Display summary
    all_status = metrics_collector.get_all_adapters_status()
    for name, status in all_status.items():
        print(f"{name}: Level {status.certification_level} ({status.certification_score:.1f}%)")


if __name__ == "__main__":
    asyncio.run(main())
