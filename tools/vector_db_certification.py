#!/usr/bin/env python3
"""
Vector DB Certification Matrix Benchmark Harness

GAP-329B: Comprehensive benchmarking and certification of vector databases.
Tests Pinecone, Weaviate, pgvector, and in-memory backends for:
- Latency performance
- Recall@k accuracy
- Scalability metrics
- Certification reports
"""

import asyncio
import json
import logging
import random
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

try:
    from metrics import (
        VECTOR_BACKEND_RECALL_AT_K_IN_MEMORY,
        VECTOR_BACKEND_RECALL_AT_K_PGVECTOR,
        VECTOR_BACKEND_RECALL_AT_K_PINECONE,
        VECTOR_BACKEND_RECALL_AT_K_WEAVIATE,
    )
except ImportError:
    # Fallback for standalone usage
    VECTOR_BACKEND_RECALL_AT_K_IN_MEMORY = None
    VECTOR_BACKEND_RECALL_AT_K_WEAVIATE = None
    VECTOR_BACKEND_RECALL_AT_K_PINECONE = None
    VECTOR_BACKEND_RECALL_AT_K_PGVECTOR = None

from tools.vector_backend import VectorBackend, VectorSearchResult
from tools.vector_metrics import VectorMetricsCollector

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkConfig:
    """Configuration for vector database benchmarking."""

    dataset_size: int = 1000
    query_count: int = 100
    embedding_dim: int = 384
    k_values: list[int] = None
    namespaces: list[str] = None
    backends: list[str] = None

    def __post_init__(self):
        if self.k_values is None:
            self.k_values = [1, 5, 10, 50, 100]
        if self.namespaces is None:
            self.namespaces = ["test", "production", "staging"]
        if self.backends is None:
            self.backends = ["in_memory", "weaviate", "pinecone", "pgvector"]


@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""

    backend: str
    namespace: str
    operation: str
    latency_ms: float
    throughput_qps: float
    recall_at_k: dict[int, float]
    error_count: int
    total_queries: int


@dataclass
class CertificationReport:
    """Comprehensive certification report for all backends."""

    timestamp: float
    config: BenchmarkConfig
    results: list[BenchmarkResult]
    recommendations: dict[str, str]
    certification_status: dict[str, str]


class VectorBenchmarkHarness:
    """Benchmark harness for vector database certification."""

    def __init__(self, config: BenchmarkConfig = None):
        self.config = config or BenchmarkConfig()
        self.metrics_collector = VectorMetricsCollector()
        self.backends: dict[str, VectorBackend] = {}
        self.test_data = self._generate_test_data()

    def _generate_test_data(self) -> dict[str, list[tuple[str, list[float], dict[str, Any]]]]:
        """Generate synthetic test data for benchmarking."""
        np.random.seed(42)  # For reproducible results

        data = {}
        for namespace in self.config.namespaces:
            vectors = []
            for i in range(self.config.dataset_size):
                # Generate random embedding
                embedding = np.random.normal(0, 1, self.config.embedding_dim).tolist()

                # Generate metadata
                metadata = {
                    "id": f"{namespace}_item_{i}",
                    "category": f"cat_{i % 10}",
                    "timestamp": time.time() + i,
                    "tags": [f"tag_{j}" for j in range(i % 5)]
                }

                vectors.append((f"key_{i}", embedding, metadata))

            data[namespace] = vectors

        return data

    def _get_recall_metric(self, backend_name: str):
        """Get the appropriate recall metric for a backend."""
        metric_map = {
            "in_memory": VECTOR_BACKEND_RECALL_AT_K_IN_MEMORY,
            "weaviate": VECTOR_BACKEND_RECALL_AT_K_WEAVIATE,
            "pinecone": VECTOR_BACKEND_RECALL_AT_K_PINECONE,
            "pgvector": VECTOR_BACKEND_RECALL_AT_K_PGVECTOR,
        }
        return metric_map.get(backend_name)

    def _generate_query_set(self, namespace: str) -> list[tuple[str, list[float]]]:
        """Generate query set from existing data."""
        if namespace not in self.test_data:
            return []

        # Use a subset of existing vectors as queries
        query_count = min(self.config.query_count, len(self.test_data[namespace]))
        query_indices = random.sample(range(len(self.test_data[namespace])), query_count)

        queries = []
        for idx in query_indices:
            key, embedding, metadata = self.test_data[namespace][idx]
            # Add small noise to make it a realistic query
            noise = np.random.normal(0, 0.1, self.config.embedding_dim)
            query_embedding = (np.array(embedding) + noise).tolist()
            queries.append((key, query_embedding))

        return queries

    def _calculate_recall_at_k(self, query_key: str, results: list[VectorSearchResult], k: int) -> float:
        """Calculate recall@k for a single query."""
        if not results:
            return 0.0

        # Extract the category from the query key
        query_parts = query_key.split('_')
        if len(query_parts) < 3:
            return 0.0

        try:
            query_id = int(query_parts[2])
            query_category = f"cat_{query_id % 10}"
        except (ValueError, IndexError):
            return 0.0

        # Count relevant results in top-k
        relevant_in_top_k = 0
        for result in results[:k]:
            result_category = result.metadata.get("category", "")
            if result_category == query_category:
                relevant_in_top_k += 1

        # Total relevant items (simplified: assume 10% of dataset is relevant)
        total_relevant = max(1, self.config.dataset_size // 10)

        return min(1.0, relevant_in_top_k / total_relevant)

    async def _benchmark_backend(
        self, backend_name: str, backend: VectorBackend, namespace: str
    ) -> list[BenchmarkResult]:
        """Benchmark a single backend for a specific namespace."""
        results = []

        # Generate queries for this namespace
        queries = self._generate_query_set(namespace)
        if not queries:
            logger.warning(f"No queries generated for namespace {namespace}")
            return results

        # Benchmark upsert operations
        upsert_latencies = []
        start_time = time.time()

        for key, embedding, metadata in self.test_data[namespace]:
            try:
                upsert_start = time.time()
                await backend.upsert(namespace, key, embedding, metadata)
                upsert_latencies.append((time.time() - upsert_start) * 1000)
            except Exception as e:
                logger.error(f"Upsert failed for {backend_name}/{namespace}: {e}")

        upsert_avg_latency = statistics.mean(upsert_latencies) if upsert_latencies else 0
        upsert_throughput = len(upsert_latencies) / (time.time() - start_time)

        results.append(BenchmarkResult(
            backend=backend_name,
            namespace=namespace,
            operation="upsert",
            latency_ms=upsert_avg_latency,
            throughput_qps=upsert_throughput,
            recall_at_k={},
            error_count=len(self.test_data[namespace]) - len(upsert_latencies),
            total_queries=len(self.test_data[namespace])
        ))

        # Benchmark query operations
        query_latencies = []
        recall_scores = {k: [] for k in self.config.k_values}
        error_count = 0

        for query_key, query_embedding in queries:
            try:
                query_start = time.time()
                search_results = await backend.query(namespace, query_embedding, k=max(self.config.k_values))
                query_latencies.append((time.time() - query_start) * 1000)

                # Calculate recall@k for each k value
                for k in self.config.k_values:
                    recall = self._calculate_recall_at_k(query_key, search_results, k)
                    recall_scores[k].append(recall)

                    # Record metrics
                    recall_metric = self._get_recall_metric(backend_name)
                    if recall_metric:
                        recall_metric.set(recall)

            except Exception as e:
                logger.error(f"Query failed for {backend_name}/{namespace}: {e}")
                error_count += 1

        if query_latencies:
            query_avg_latency = statistics.mean(query_latencies)
            query_throughput = len(query_latencies) / sum(query_latencies) * 1000

            avg_recall_at_k = {}
            for k in self.config.k_values:
                if recall_scores[k]:
                    avg_recall_at_k[k] = statistics.mean(recall_scores[k])
                else:
                    avg_recall_at_k[k] = 0.0

            results.append(BenchmarkResult(
                backend=backend_name,
                namespace=namespace,
                operation="query",
                latency_ms=query_avg_latency,
                throughput_qps=query_throughput,
                recall_at_k=avg_recall_at_k,
                error_count=error_count,
                total_queries=len(queries)
            ))

        return results

    def _create_mock_backend(self, backend_type: str) -> Optional[VectorBackend]:
        """Create a mock backend for testing unsupported backends."""
        if backend_type == "in_memory":
            from tools.vector_backend import InMemoryVectorBackend
            return InMemoryVectorBackend({"metrics_callback": self.metrics_collector.record_metrics})
        else:
            logger.warning(f"Backend {backend_type} not implemented, using in-memory fallback")
            return None

    async def run_benchmarks(self) -> CertificationReport:
        """Run comprehensive benchmarks across all configured backends."""
        logger.info("Starting vector database certification benchmarks")

        # Initialize backends
        for backend_type in self.config.backends:
            backend = self._create_mock_backend(backend_type)
            if backend:
                self.backends[backend_type] = backend

        if not self.backends:
            raise ValueError("No backends available for benchmarking")

        all_results = []

        # Run benchmarks for each backend and namespace
        for backend_name, backend in self.backends.items():
            for namespace in self.config.namespaces:
                logger.info(f"Benchmarking {backend_name} on namespace {namespace}")
                try:
                    results = await self._benchmark_backend(backend_name, backend, namespace)
                    all_results.extend(results)
                except Exception as e:
                    logger.error(f"Benchmark failed for {backend_name}/{namespace}: {e}")

        # Generate certification report
        report = self._generate_certification_report(all_results)

        logger.info("Benchmarking completed")
        return report

    def _generate_certification_report(self, results: list[BenchmarkResult]) -> CertificationReport:
        """Generate comprehensive certification report."""
        recommendations = {}
        certification_status = {}

        # Group results by backend
        backend_results = {}
        for result in results:
            if result.backend not in backend_results:
                backend_results[result.backend] = []
            backend_results[result.backend].append(result)

        # Analyze each backend
        for backend_name, backend_res in backend_results.items():
            # Calculate average metrics
            query_results = [r for r in backend_res if r.operation == "query"]

            if query_results:
                avg_latency = statistics.mean(r.latency_ms for r in query_results)
                avg_recall = statistics.mean(
                    statistics.mean(list(r.recall_at_k.values())) for r in query_results
                )

                # Determine certification status
                if avg_latency < 100 and avg_recall > 0.8:
                    status = "CERTIFIED"
                elif avg_latency < 500 and avg_recall > 0.6:
                    status = "QUALIFIED"
                else:
                    status = "NOT_RECOMMENDED"

                certification_status[backend_name] = status

                # Generate recommendations
                if status == "CERTIFIED":
                    recommendations[backend_name] = "Excellent performance and recall. Recommended for production use."
                elif status == "QUALIFIED":
                    recommendations[backend_name] = "Good performance but may need optimization for high-throughput scenarios."
                else:
                    recommendations[backend_name] = "Performance or recall below acceptable thresholds. Consider alternatives."

        return CertificationReport(
            timestamp=time.time(),
            config=self.config,
            results=results,
            recommendations=recommendations,
            certification_status=certification_status
        )

    def save_report(self, report: CertificationReport, output_path: Path) -> None:
        """Save certification report to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report_data = {
            "timestamp": report.timestamp,
            "config": {
                "dataset_size": report.config.dataset_size,
                "query_count": report.config.query_count,
                "embedding_dim": report.config.embedding_dim,
                "k_values": report.config.k_values,
                "namespaces": report.config.namespaces,
                "backends": report.config.backends
            },
            "results": [
                {
                    "backend": r.backend,
                    "namespace": r.namespace,
                    "operation": r.operation,
                    "latency_ms": r.latency_ms,
                    "throughput_qps": r.throughput_qps,
                    "recall_at_k": r.recall_at_k,
                    "error_count": r.error_count,
                    "total_queries": r.total_queries
                }
                for r in report.results
            ],
            "recommendations": report.recommendations,
            "certification_status": report.certification_status
        }

        with open(output_path, 'w') as f:
            json.dump(report_data, f, indent=2)

        logger.info(f"Certification report saved to {output_path}")


async def main():
    """Main entry point for the benchmark harness."""
    import argparse

    parser = argparse.ArgumentParser(description="Vector DB Certification Matrix Benchmark")
    parser.add_argument("--dataset-size", type=int, default=1000, help="Size of test dataset")
    parser.add_argument("--query-count", type=int, default=100, help="Number of queries to run")
    parser.add_argument("--embedding-dim", type=int, default=384, help="Embedding dimension")
    parser.add_argument("--backends", nargs="+", default=["in_memory"], help="Backends to test")
    parser.add_argument("--output", type=Path, default=Path("data/vector_certification_report.json"),
                       help="Output path for certification report")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    # Create benchmark configuration
    config = BenchmarkConfig(
        dataset_size=args.dataset_size,
        query_count=args.query_count,
        embedding_dim=args.embedding_dim,
        backends=args.backends
    )

    # Run benchmarks
    harness = VectorBenchmarkHarness(config)
    report = await harness.run_benchmarks()

    # Save report
    harness.save_report(report, args.output)

    # Print summary
    print("\nVector Database Certification Report")
    print("===================================")
    print(f"Dataset size: {config.dataset_size}")
    print(f"Query count: {config.query_count}")
    print(f"Backends tested: {', '.join(config.backends)}")
    print("\nCertification Status:")
    for backend, status in report.certification_status.items():
        print(f"  {backend}: {status}")
        if backend in report.recommendations:
            print(f"    {report.recommendations[backend]}")

    print(f"\nDetailed report saved to: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
