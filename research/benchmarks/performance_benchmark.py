#!/usr/bin/env python3
"""
Performance Benchmark for ATP Build Optimizations

This script benchmarks the performance improvements from the build optimizations:
- Parallel processing vs sequential
- Build caching effectiveness
- Docker optimization impact
- Dependency optimization benefits
"""

import concurrent.futures
import subprocess
import sys
import time
from pathlib import Path


class PerformanceBenchmark:
    """Benchmark build performance improvements."""

    def __init__(self):
        self.results: dict[str, dict] = {}

    def _run_command(self, cmd: list[str], cwd: str = None) -> tuple[int, str, str]:
        """Run a command and return exit code, stdout, stderr."""
        try:
            result = subprocess.run(  # noqa: S603 - controlled benchmarking commands
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except FileNotFoundError:
            return -1, "", "Command not found"

    def benchmark_sequential_vs_parallel(self) -> dict:
        """Benchmark sequential vs parallel build validation."""
        print("🔬 Benchmarking: Sequential vs Parallel Processing")

        # Sequential validation (simulate old approach)
        start_time = time.time()
        components = ['memory-gateway', 'persona-adapter', 'ollama-adapter']

        sequential_times = []
        for component in components:
            comp_start = time.time()
            if component == 'memory-gateway':
                exit_code, _, _ = self._run_command([sys.executable, "-m", "py_compile", "memory-gateway/app.py"])
            else:
                exit_code, _, _ = self._run_command([sys.executable, "-m", "py_compile", f"adapters/python/{component}/main.py"])
            comp_time = time.time() - comp_start
            sequential_times.append(comp_time)

        sequential_total = time.time() - start_time

        # Parallel validation (current optimized approach)
        start_time = time.time()

        def validate_component(component: str) -> float:
            comp_start = time.time()
            if component == 'memory-gateway':
                exit_code, _, _ = self._run_command([sys.executable, "-m", "py_compile", "memory-gateway/app.py"])
            else:
                exit_code, _, _ = self._run_command([sys.executable, "-m", "py_compile", f"adapters/python/{component}/main.py"])
            return time.time() - comp_start

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            parallel_times = list(executor.map(validate_component, components))

        parallel_total = time.time() - start_time

        return {
            'sequential_total': sequential_total,
            'parallel_total': parallel_total,
            'speedup_ratio': sequential_total / parallel_total if parallel_total > 0 else 1,
            'sequential_times': sequential_times,
            'parallel_times': parallel_times
        }

    def benchmark_dependency_installation(self) -> dict:
        """Benchmark dependency installation time."""
        print("🔬 Benchmarking: Dependency Installation")

        # Original requirements (if exists)
        original_req = Path("requirements.txt")
        optimized_req = Path("requirements_optimized.txt")

        results = {}

        if original_req.exists():
            start_time = time.time()
            exit_code, _, _ = self._run_command([sys.executable, "-m", "pip", "install", "--dry-run", "-r", str(original_req)])
            results['original_time'] = time.time() - start_time
            results['original_packages'] = self._count_packages(original_req)
        else:
            results['original_time'] = 0
            results['original_packages'] = 0

        if optimized_req.exists():
            start_time = time.time()
            exit_code, _, _ = self._run_command([sys.executable, "-m", "pip", "install", "--dry-run", "-r", str(optimized_req)])
            results['optimized_time'] = time.time() - start_time
            results['optimized_packages'] = self._count_packages(optimized_req)
        else:
            results['optimized_time'] = 0
            results['optimized_packages'] = 0

        if results['original_time'] > 0 and results['optimized_time'] > 0:
            results['dependency_speedup'] = results['original_time'] / results['optimized_time']
            results['package_reduction'] = ((results['original_packages'] - results['optimized_packages']) / results['original_packages']) * 100

        return results

    def _count_packages(self, req_file: Path) -> int:
        """Count packages in requirements file."""
        if not req_file.exists():
            return 0

        count = 0
        with open(req_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    count += 1
        return count

    def benchmark_caching_effectiveness(self) -> dict:
        """Benchmark build caching effectiveness."""
        print("🔬 Benchmarking: Build Caching")

        # Run build validator twice to test caching
        results = {}

        # First run (should do actual work)
        start_time = time.time()
        exit_code1, _, _ = self._run_command([sys.executable, "tools/build_validator.py"])
        first_run_time = time.time() - start_time

        # Second run (should use cache)
        start_time = time.time()
        exit_code2, _, _ = self._run_command([sys.executable, "tools/build_validator.py"])
        second_run_time = time.time() - start_time

        results['first_run_time'] = first_run_time
        results['second_run_time'] = second_run_time
        results['cache_speedup'] = first_run_time / second_run_time if second_run_time > 0 else 1
        results['time_saved'] = first_run_time - second_run_time

        return results

    def run_all_benchmarks(self) -> dict:
        """Run all performance benchmarks."""
        print("🚀 Starting ATP Build Performance Benchmarks")
        print("=" * 50)

        self.results = {
            'processing_benchmark': self.benchmark_sequential_vs_parallel(),
            'dependency_benchmark': self.benchmark_dependency_installation(),
            'caching_benchmark': self.benchmark_caching_effectiveness()
        }

        return self.results

    def print_results(self):
        """Print benchmark results in a nice format."""
        if not self.results:
            print("❌ No benchmark results available. Run benchmarks first.")
            return

        print("\n📊 ATP Build Optimization Performance Results")
        print("=" * 60)

        # Processing benchmark
        proc = self.results.get('processing_benchmark', {})
        if proc:
            print("🔄 Processing Optimization:")
            print(".2f")
            print(".2f")
            print(".1f")
            print()

        # Dependency benchmark
        dep = self.results.get('dependency_benchmark', {})
        if dep:
            print("📦 Dependency Optimization:")
            if dep.get('original_packages', 0) > 0:
                print(f"  Original packages: {dep['original_packages']}")
                print(f"  Optimized packages: {dep['optimized_packages']}")
                print(".1f")
            if 'dependency_speedup' in dep:
                print(".1f")
            print()

        # Caching benchmark
        cache = self.results.get('caching_benchmark', {})
        if cache:
            print("💾 Build Caching:")
            print(".2f")
            print(".2f")
            print(".1f")
            print(".2f")
            print()

        print("✅ All benchmarks completed!")


def main():
    """Main benchmark execution."""
    benchmark = PerformanceBenchmark()
    benchmark.run_all_benchmarks()
    benchmark.print_results()


if __name__ == "__main__":
    main()
