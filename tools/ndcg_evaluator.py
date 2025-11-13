"""GAP-306: NDCG@k Evaluator Harness for Ranking & Relevance Quality Metrics."""

from __future__ import annotations

import math
from typing import Any

from metrics.registry import REGISTRY


class NDCGEvaluator:
    """NDCG@k evaluator for ranking quality assessment."""

    def __init__(self, k_values: list[int] | None = None):
        self.k_values = k_values or [1, 3, 5, 10]
        self.ndcg_avg_metric = REGISTRY.histogram(
            "vector_ndcg_avg", buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        )

    def dcg_at_k(self, relevance_scores: list[float], k: int) -> float:
        dcg = 0.0
        for i in range(min(k, len(relevance_scores))):
            dcg += relevance_scores[i] / math.log2(i + 2)
        return dcg

    def idcg_at_k(self, ideal_relevance_scores: list[float], k: int) -> float:
        ideal_sorted = sorted(ideal_relevance_scores, reverse=True)
        return self.dcg_at_k(ideal_sorted, k)

    def ndcg_at_k(self, relevance_scores: list[float], k: int) -> float:
        dcg = self.dcg_at_k(relevance_scores, k)
        idcg = self.idcg_at_k(relevance_scores, k)
        if idcg == 0:
            return 0.0
        return dcg / idcg

    def evaluate_ranking(
        self, ranked_items: list[dict[str, Any]], relevance_judgments: dict[str, float]
    ) -> dict[str, float]:
        relevance_scores = []
        for item in ranked_items:
            key = item.get("key", item.get("id", str(item)))
            relevance = relevance_judgments.get(key, 0.0)
            relevance_scores.append(relevance)

        results = {}
        for k in self.k_values:
            ndcg_score = self.ndcg_at_k(relevance_scores, k)
            results[f"ndcg@{k}"] = ndcg_score
            self.ndcg_avg_metric.observe(ndcg_score)

        return results

    def compare_rankings(
        self,
        baseline_ranking: list[dict[str, Any]],
        improved_ranking: list[dict[str, Any]],
        relevance_judgments: dict[str, float],
    ) -> dict[str, Any]:
        baseline_scores = self.evaluate_ranking(baseline_ranking, relevance_judgments)
        improved_scores = self.evaluate_ranking(improved_ranking, relevance_judgments)

        comparison = {"baseline": baseline_scores, "improved": improved_scores, "improvement": {}}

        for k in self.k_values:
            key = f"ndcg@{k}"
            baseline_score = baseline_scores[key]
            improved_score = improved_scores[key]

            if baseline_score > 0:
                improvement_pct = ((improved_score - baseline_score) / baseline_score) * 100
            else:
                improvement_pct = 0.0 if improved_score == 0 else float("inf")

            comparison["improvement"][f"{key}_improvement_pct"] = improvement_pct

        return comparison


def create_synthetic_evaluation_data(
    num_items: int = 20, embedding_dim: int = 128, num_relevant: int = 5
) -> tuple[list[dict[str, Any]], list[float], dict[str, float]]:
    import random

    import numpy as np

    random.seed(42)
    np.random.seed(42)

    query_embedding = np.random.normal(0, 1, embedding_dim).tolist()

    items = []
    relevance_judgments = {}

    for i in range(num_items):
        if i < num_relevant:
            noise = np.random.normal(0, 0.1, embedding_dim)
            embedding = (np.array(query_embedding) + noise).tolist()
            relevance = 0.9 + random.uniform(-0.1, 0.1)
        else:
            embedding = np.random.normal(0, 1, embedding_dim).tolist()
            relevance = random.uniform(0.1, 0.7)

        item = {"key": f"item_{i}", "embedding": embedding, "metadata": {"index": i}}
        items.append(item)
        relevance_judgments[f"item_{i}"] = relevance

    return items, query_embedding, relevance_judgments


_evaluator = None


def get_evaluator() -> NDCGEvaluator:
    global _evaluator
    if _evaluator is None:
        _evaluator = NDCGEvaluator()
    return _evaluator
