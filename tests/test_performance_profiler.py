"""Tests for performance profiling utilities."""

import time

from tools.performance_profiler import (
    PerformanceProfiler,
    ProfileResult,
    get_profiler,
    profile_function,
)


def test_profile_function_context_manager():
    """Test profiling with context manager."""
    profiler = PerformanceProfiler()

    with profiler.profile_function("test_function"):
        time.sleep(0.01)  # Simulate some work

    result = profiler.get_profile_report("test_function")
    assert result is not None
    assert result.function_name == "test_function"
    assert result.total_time >= 0.01
    assert result.call_count == 1


def test_profile_decorator():
    """Test profiling with decorator."""
    profiler = PerformanceProfiler()

    @profiler.profile_decorator("decorated_function")
    def test_func():
        time.sleep(0.01)
        return "done"

    result = test_func()
    assert result == "done"

    profile_result = profiler.get_profile_report("decorated_function")
    assert profile_result is not None
    assert profile_result.total_time >= 0.01


def test_performance_report_generation():
    """Test performance report generation."""
    profiler = PerformanceProfiler()

    # Add some mock profile results
    profiler.profiles["func1"] = ProfileResult(
        function_name="func1",
        total_time=0.1,
        call_count=1,
        avg_time=0.1,
        cumulative_time=0.1
    )
    profiler.profiles["func2"] = ProfileResult(
        function_name="func2",
        total_time=0.2,
        call_count=1,
        avg_time=0.2,
        cumulative_time=0.2
    )

    report = profiler.generate_report("test_endpoint")

    assert report.endpoint == "test_endpoint"
    assert report.total_requests == 2
    assert report.avg_response_time == 0.15
    assert len(report.slow_operations) == 2
    assert report.slow_operations[0].function_name == "func2"  # Should be sorted by time


def test_percentile_calculation():
    """Test percentile calculation."""
    profiler = PerformanceProfiler()

    values = [0.1, 0.2, 0.3, 0.4, 0.5]
    p95 = profiler._calculate_percentile(values, 95)
    assert p95 == 0.5  # 95th percentile of [0.1, 0.2, 0.3, 0.4, 0.5] is 0.5

    p50 = profiler._calculate_percentile(values, 50)
    assert p50 == 0.3  # 50th percentile (median) is 0.3


def test_global_profiler():
    """Test global profiler instance."""
    profiler = get_profiler()
    assert isinstance(profiler, PerformanceProfiler)

    # Test that we can use the global profiler
    with profile_function("global_test"):
        time.sleep(0.001)

    result = profiler.get_profile_report("global_test")
    assert result is not None


def test_profile_with_cprofile():
    """Test profiling with cProfile enabled."""
    profiler = PerformanceProfiler()

    with profiler.profile_function("cprofile_test", enable_cprofile=True):
        # Simple function to profile
        _total = sum(range(1000))

    result = profiler.get_profile_report("cprofile_test")
    assert result is not None
    assert result.profile_data is not None
    assert "function calls" in result.profile_data.lower()


def test_decorator_with_cprofile():
    """Test decorator with cProfile enabled."""
    profiler = PerformanceProfiler()

    @profiler.profile_decorator("cprofile_decorated", enable_cprofile=True)
    def test_function():
        return sum(range(1000))

    result = test_function()
    assert result == sum(range(1000))

    profile_result = profiler.get_profile_report("cprofile_decorated")
    assert profile_result is not None
    assert profile_result.profile_data is not None


def test_clear_profiles():
    """Test clearing profiles."""
    profiler = PerformanceProfiler()

    profiler.profiles["test"] = ProfileResult(
        function_name="test",
        total_time=0.1,
        call_count=1,
        avg_time=0.1,
        cumulative_time=0.1
    )

    assert len(profiler.profiles) == 1
    profiler.clear_profiles()
    assert len(profiler.profiles) == 0
