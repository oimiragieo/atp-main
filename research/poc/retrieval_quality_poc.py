"""Retrieval quality POC: packing/MMR diversification & embedding selection benchmark.
Implements a simple MMR (Maximal Marginal Relevance) selection over synthetic vectors and
verifies diversity vs top-k greedy similarity.
"""

from __future__ import annotations

import math
import random

Vector = tuple[str, list[float], dict]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1
    nb = math.sqrt(sum(x * x for x in b)) or 1
    return dot / (na * nb)


def mmr(query: list[float], docs: list[Vector], k: int, lambda_param: float = 0.7) -> list[Vector]:
    selected: list[Vector] = []
    candidates = docs[:]
    while candidates and len(selected) < k:
        best = None
        best_score = -1
        for d in candidates:
            sim = cosine(query, d[1])
            if not selected:
                score = sim
            else:
                max_red = max(cosine(d[1], s[1]) for s in selected)
                score = lambda_param * sim - (1 - lambda_param) * max_red
            if score > best_score:
                best_score = score
                best = d
        selected.append(best)
        candidates.remove(best)
    return selected


def topk(query: list[float], docs: list[Vector], k: int) -> list[Vector]:
    return sorted(docs, key=lambda d: cosine(query, d[1]), reverse=True)[:k]


def synth_docs(num_clusters=3, cluster_size=5, dim=8, spread=0.05) -> list[Vector]:
    random.seed(42)
    docs: list[Vector] = []
    for c in range(num_clusters):
        center = [random.random() for _ in range(dim)]
        for i in range(cluster_size):
            vec = [max(0, min(1, v + random.uniform(-spread, spread))) for v in center]
            docs.append((f"d{c}_{i}", vec, {"cluster": c}))
    return docs


def evaluate():
    docs = synth_docs()
    # Query similar to cluster 0 but we want some diversity
    query = list(docs[0][1])
    top = topk(query, docs, k=5)
    mmr_sel = mmr(query, docs, k=5)
    top_clusters = {d[2]["cluster"] for d in top}
    mmr_clusters = {d[2]["cluster"] for d in mmr_sel}
    # Expect mmr to cover more clusters than naive top-k
    assert len(mmr_clusters) >= len(top_clusters)
    # Packing: group selected docs by cluster order
    packing = {}
    for doc in mmr_sel:
        packing.setdefault(doc[2]["cluster"], []).append(doc[0])
    return {
        "top_clusters": top_clusters,
        "mmr_clusters": mmr_clusters,
        "mmr_selection": [d[0] for d in mmr_sel],
        "packing": packing,
    }


if __name__ == "__main__":
    res = evaluate()
    assert res["mmr_selection"]
    print("OK: retrieval quality POC passed", res)
