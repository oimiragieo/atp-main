"""Simple performance profiling utilities for ATP system.

Provides lightweight timing, an optional cProfile-based deep profiler,
and helpers to generate human-friendly reports. Designed to be safe in
tests and production alike.
"""

import contextlib
import cProfile
import io
import json
import pstats
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path


@dataclass
class ProfileResult:
    """Result of a profiling operation."""

    function_name: str
    total_time: float
    call_count: int
    avg_time: float
    # Optional aggregate or externally provided cumulative timing
    cumulative_time: float | None = None
    # Optional serialized cProfile stats text
    profile_data: str | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class PerformanceReport:
    """Performance report."""

    endpoint: str
    total_requests: int
    avg_response_time: float
    slow_operations: list[ProfileResult] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class PerformanceProfiler:
    """Simple performance profiling class."""

    def __init__(self, output_dir: str = "performance_reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.profiles: dict[str, ProfileResult] = {}
        self.start_times: dict[str, float] = {}

    def start_profile(self, name: str):
        """Start profiling a function."""
        self.start_times[name] = time.perf_counter()

    def end_profile(self, name: str):
        """End profiling a function."""
        if name not in self.start_times:
            return

        end_time = time.perf_counter()
        total_time = end_time - self.start_times[name]

        # Update or create profile result
        if name in self.profiles:
            existing = self.profiles[name]
            new_call_count = existing.call_count + 1
            new_total_time = existing.total_time + total_time
            self.profiles[name] = ProfileResult(
                function_name=name,
                total_time=new_total_time,
                call_count=new_call_count,
                avg_time=new_total_time / new_call_count,
                cumulative_time=(existing.cumulative_time or 0.0) + total_time,
                profile_data=existing.profile_data,
            )
        else:
            self.profiles[name] = ProfileResult(
                function_name=name,
                total_time=total_time,
                call_count=1,
                avg_time=total_time,
                cumulative_time=total_time,
            )

        del self.start_times[name]

    @contextlib.contextmanager
    def profile_function(self, name: str, *, enable_cprofile: bool = False) -> Iterator[None]:
        """Context manager that profiles a code block as a named function.

        If `enable_cprofile` is True, captures and stores a textual summary
        of cProfile statistics in the corresponding ProfileResult.
        """
        profiler: cProfile.Profile | None = None
        s: io.StringIO | None = None
        try:
            if enable_cprofile:
                profiler = cProfile.Profile()
                profiler.enable()

            self.start_profile(name)
            yield
        finally:
            # Finish timers first
            self.end_profile(name)

            # Then capture cProfile stats if enabled
            if profiler is not None:
                profiler.disable()
                s = io.StringIO()
                ps = pstats.Stats(profiler, stream=s).sort_stats(pstats.SortKey.CUMULATIVE)
                ps.print_stats()
                stats_text = s.getvalue()
                # Attach profile_data to the latest ProfileResult
                pr = self.profiles.get(name)
                if pr is not None:
                    self.profiles[name] = ProfileResult(
                        function_name=pr.function_name,
                        total_time=pr.total_time,
                        call_count=pr.call_count,
                        avg_time=pr.avg_time,
                        cumulative_time=pr.cumulative_time,
                        profile_data=stats_text,
                        timestamp=pr.timestamp,
                    )

    def profile_decorator(self, name: str, *, enable_cprofile: bool = False):
        """Decorator to profile a function by name.

        Usage:
            @profiler.profile_decorator("op")
            def f(...): ...
        """

        def _decorator(func):
            @wraps(func)
            def _wrapped(*args, **kwargs):
                with self.profile_function(name, enable_cprofile=enable_cprofile):
                    return func(*args, **kwargs)

            return _wrapped

        return _decorator

    def get_profile_report(self, name: str) -> ProfileResult | None:
        """Return profiling result for a given name, if any."""
        return self.profiles.get(name)

    def generate_report(self, endpoint: str = "system") -> PerformanceReport:
        """Generate a performance report."""
        total_operations = len(self.profiles)
        if total_operations == 0:
            avg_time = 0.0
        else:
            avg_time = sum(p.total_time for p in self.profiles.values()) / total_operations
            # Normalize tiny float diffs for deterministic tests
            avg_time = round(avg_time, 10)

        # Find slow operations (top 5 by total time)
        slow_ops = sorted(self.profiles.values(), key=lambda x: x.total_time, reverse=True)[:5]

        return PerformanceReport(
            endpoint=endpoint,
            total_requests=total_operations,
            avg_response_time=avg_time,
            slow_operations=slow_ops,
        )

    def save_report(self, report: PerformanceReport, filename: str | None = None) -> str:
        """Save performance report to file."""
        if filename is None:
            timestamp = int(time.time())
            filename = f"performance_report_{report.endpoint}_{timestamp}.json"

        filepath = self.output_dir / filename

        report_data = {
            "endpoint": report.endpoint,
            "total_requests": report.total_requests,
            "avg_response_time": report.avg_response_time,
            "timestamp": report.timestamp,
            "slow_operations": [
                {
                    "function_name": op.function_name,
                    "total_time": op.total_time,
                    "call_count": op.call_count,
                    "avg_time": op.avg_time,
                }
                for op in report.slow_operations
            ],
        }

        with open(filepath, "w") as f:
            json.dump(report_data, f, indent=2)

        print(f"Performance report saved to {filepath}")
        return str(filepath)

    # --- Test helpers / analytics ---
    def clear_profiles(self) -> None:
        """Clear all collected profile data."""
        self.profiles.clear()
        self.start_times.clear()

    def _calculate_percentile(self, values: list[float], percentile: float) -> float:
        """Calculate a simple percentile using nearest-rank method."""
        if not values:
            return 0.0
        vals = sorted(values)
        idx = _percentile_index(len(vals), percentile)
        return vals[idx]


# Global profiler instance
_profiler = PerformanceProfiler()


def get_profiler() -> PerformanceProfiler:
    """Get the global profiler instance."""
    return _profiler


@contextlib.contextmanager
def profile_function(name: str, *, enable_cprofile: bool = False) -> Iterator[None]:
    """Module-level context manager that profiles using the global profiler."""
    with _profiler.profile_function(name, enable_cprofile=enable_cprofile):
        yield


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _percentile_index(n: int, percentile: float) -> int:
    # PERCENTILE: simple nearest-rank method
    if n == 0:
        return 0
    p = _clamp(percentile, 0.0, 100.0)
    rank = int(round((p / 100.0) * (n - 1)))
    return max(0, min(n - 1, rank))


def _sorted(values):
    try:
        return sorted(values)
    except Exception:
        return list(values)


def run_performance_benchmark():
    """Run performance benchmark."""
    profiler = get_profiler()

    # Run fragmentation benchmark
    try:
        import os
        # Try importing the benchmark from tools first; fallback to root for legacy paths

        # Set minimal environment variables to avoid config errors
        if "ROUTER_ADMIN_API_KEY" not in os.environ:
            os.environ["ROUTER_ADMIN_API_KEY"] = "benchmark-key"

        try:
            from tools.fragmentation_benchmark_poc import run_benchmark as frag_benchmark  # type: ignore
        except Exception:  # pragma: no cover - legacy import path
            from fragmentation_benchmark_poc import run_benchmark as frag_benchmark  # type: ignore

        profiler.start_profile("fragmentation_benchmark")
        result = frag_benchmark()
        profiler.end_profile("fragmentation_benchmark")

        print(f"Fragmentation benchmark: {result.fragments} fragments in {result.elapsed_ms:.3f}ms")
    except Exception as e:
        print(f"Skipping fragmentation benchmark: {e}")

    # Generate and save report
    report = profiler.generate_report("benchmark")
    filepath = profiler.save_report(report)

    print(f"Performance benchmark completed. Report saved to: {filepath}")

    return report


if __name__ == "__main__":
    run_performance_benchmark()
