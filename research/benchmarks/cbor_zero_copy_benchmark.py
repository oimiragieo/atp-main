#!/usr/bin/env python3
"""CBOR Zero-Copy Performance Benchmark.

This script benchmarks the performance difference between regular CBOR encoding
and zero-copy CBOR encoding to demonstrate the efficiency gains.
"""

import statistics
import time
from io import BytesIO
from typing import Any

from tools.atp_cbor_codec_poc import (
    _encode_cbor,
    _encode_cbor_zero_copy,
    encode_frame,
    encode_frame_zero_copy,
)


def create_test_frame(size: str = "medium") -> dict[str, Any]:
    """Create a test frame of specified size."""
    if size == "small":
        return {
            "v": 1,
            "session_id": "s1",
            "stream_id": "st1",
            "msg_seq": 1,
            "frag_seq": 0,
            "flags": ["SYN"],
            "qos": "gold",
            "ttl": 8,
        }
    elif size == "medium":
        return {
            "v": 1,
            "session_id": "session_123456789",
            "stream_id": "stream_abcdef123",
            "msg_seq": 42,
            "frag_seq": 3,
            "flags": ["SYN", "ACK"],
            "qos": "platinum",
            "ttl": 30,
            "window": {
                "max_parallel": 10,
                "max_tokens": 8192,
                "max_usd_micros": 500000,
            },
            "meta": {
                "task_type": "code_generation",
                "model": "gpt-4-turbo",
                "temperature": 0.7,
            },
            "payload": {
                "type": "agent.result.partial",
                "content": {
                    "text": "This is a sample response from the AI assistant.",
                    "tokens_used": 150,
                    "finish_reason": "length",
                },
            },
        }
    elif size == "large":
        # Create a large frame with repeated data
        large_content = "x" * 1000
        return {
            "v": 1,
            "session_id": "large_session_id_12345678901234567890",
            "stream_id": "large_stream_id_abcdef1234567890",
            "msg_seq": 1000,
            "frag_seq": 0,
            "flags": ["SYN", "ACK", "FIN"],
            "qos": "platinum",
            "ttl": 60,
            "window": {
                "max_parallel": 50,
                "max_tokens": 32768,
                "max_usd_micros": 2000000,
            },
            "meta": {
                "task_type": "document_analysis",
                "model": "gpt-4-turbo",
                "temperature": 0.1,
                "max_tokens": 4000,
            },
            "payload": {
                "type": "agent.result.complete",
                "content": {
                    "text": large_content,
                    "tokens_used": 2000,
                    "finish_reason": "stop",
                    "metadata": {
                        "confidence": 0.95,
                        "processing_time_ms": 2500,
                        "model_version": "2024-01-15",
                    },
                },
            },
        }


def benchmark_encoding(frame: dict[str, Any], key: bytes, iterations: int = 1000) -> dict[str, float]:
    """Benchmark encoding performance."""
    print(f"Benchmarking {iterations} iterations...")

    # Benchmark regular encoding
    regular_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        encode_frame(frame, key)
        end = time.perf_counter()
        regular_times.append(end - start)

    # Benchmark zero-copy encoding
    zero_copy_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        encode_frame_zero_copy(frame, key)
        end = time.perf_counter()
        zero_copy_times.append(end - start)

    # Benchmark just the CBOR encoding part
    cbor_regular_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        _encode_cbor(frame)
        end = time.perf_counter()
        cbor_regular_times.append(end - start)

    cbor_zero_copy_times = []
    for _ in range(iterations):
        buffer = BytesIO()
        start = time.perf_counter()
        _encode_cbor_zero_copy(frame, buffer)
        buffer.getvalue()  # Ensure buffer is fully written
        end = time.perf_counter()
        cbor_zero_copy_times.append(end - start)

    return {
        "regular_frame_mean": statistics.mean(regular_times),
        "regular_frame_std": statistics.stdev(regular_times),
        "zero_copy_frame_mean": statistics.mean(zero_copy_times),
        "zero_copy_frame_std": statistics.stdev(zero_copy_times),
        "regular_cbor_mean": statistics.mean(cbor_regular_times),
        "regular_cbor_std": statistics.stdev(cbor_regular_times),
        "zero_copy_cbor_mean": statistics.mean(cbor_zero_copy_times),
        "zero_copy_cbor_std": statistics.stdev(cbor_zero_copy_times),
    }


def run_benchmarks():
    """Run comprehensive benchmarks."""
    key = b"benchmark_key_32_bytes_long_123"

    print("CBOR Zero-Copy Performance Benchmark")
    print("=" * 50)

    for size in ["small", "medium", "large"]:
        print(f"\nTesting {size.upper()} frame:")
        print("-" * 30)

        frame = create_test_frame(size)
        results = benchmark_encoding(frame, key, 1000)

        print(".6f")
        print(".6f")
        print(".6f")
        print(".6f")

        # Calculate improvement
        frame_improvement_pct = (
            (results["regular_frame_mean"] - results["zero_copy_frame_mean"]) / results["regular_frame_mean"] * 100
        )
        cbor_improvement_pct = (
            (results["regular_cbor_mean"] - results["zero_copy_cbor_mean"]) / results["regular_cbor_mean"] * 100
        )

        print(f"Frame encoding improvement: {frame_improvement_pct:.1f}%")
        print(f"CBOR encoding improvement: {cbor_improvement_pct:.1f}%")

        # Verify correctness
        regular_result = encode_frame(frame, key)
        zero_copy_result = encode_frame_zero_copy(frame, key)

        if regular_result == zero_copy_result:
            print("✅ Results are identical")
        else:
            print("❌ Results differ - implementation error!")


def memory_usage_comparison():
    """Compare memory usage patterns."""
    import tracemalloc

    key = b"memory_test_key_32_bytes_long_"
    frame = create_test_frame("large")

    print("\nMemory Usage Comparison:")
    print("-" * 30)

    # Test regular encoding
    tracemalloc.start()
    regular_result = encode_frame(frame, key)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"Regular encoding peak memory: {peak / 1024:.1f} KB")
    print(f"Regular encoding current memory: {current / 1024:.1f} KB")

    # Test zero-copy encoding
    tracemalloc.start()
    zero_copy_result = encode_frame_zero_copy(frame, key)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"Zero-copy encoding peak memory: {peak / 1024:.1f} KB")
    print(f"Zero-copy encoding current memory: {current / 1024:.1f} KB")

    print(f"Output sizes - Regular: {len(regular_result)} bytes, Zero-copy: {len(zero_copy_result)} bytes")


if __name__ == "__main__":
    run_benchmarks()
    memory_usage_comparison()
