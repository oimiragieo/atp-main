"""Heuristic task classifier with embedding-based clustering fallback.
Maps prompt patterns / keywords to coarse cluster hints used for SLM specialist selection.
Enhanced with GAP-206: embedding-based cluster classification.
"""

import hashlib
import os
import re

from .cluster_coverage import tracker
from .embedding_cluster_classifier import EMBEDDING_CLUSTER_CLASSIFIER


def _heuristic_classify(prompt: str) -> str | None:
    """Heuristic classification fallback function."""
    lower = prompt.lower()
    for cluster, patterns in KEYWORD_CLUSTERS.items():
        for p in patterns:
            if p in lower:
                tracker.record_cluster_usage(cluster)
                return cluster
    if re.search(r"\{\s*\w+\s*:\s*", prompt):
        tracker.record_cluster_usage("json_struct")
        return "json_struct"
    # Hashed bucket fallback
    try:
        bucket_count = int(os.getenv("CLUSTER_HASH_BUCKETS", "0"))
    except ValueError:
        bucket_count = 0
    if bucket_count > 0:
        h = int(hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8], 16)
        bucket = h % bucket_count
        bucket_name = f"bucket_{bucket}"
        tracker.record_cluster_usage(bucket_name)
        return bucket_name
    return None


# Set the fallback classifier for the global instance
EMBEDDING_CLUSTER_CLASSIFIER.fallback_classifier = _heuristic_classify

KEYWORD_CLUSTERS = {
    "code": ["def ", "class ", "import ", "function", "bug"],
    "summarize": ["summarize", "tl;dr", "brief summary"],
    "extract": ["extract", "pull out", "list the"],
    "classify": ["categorize", "classify", "label"],
}


def classify(prompt: str) -> str | None:
    """Return a coarse cluster label using embedding-based clustering with heuristic fallback.
    Order:
      1. Embedding-based clustering (GAP-206)
      2. Keyword / pattern rules (fallback)
      3. Regex based json_struct intent (fallback)
      4. Optional hashed bucket fallback (env CLUSTER_HASH_BUCKETS > 0)
    """
    # Try embedding-based classification first (GAP-206)
    embedding_cluster = EMBEDDING_CLUSTER_CLASSIFIER.classify_task(prompt)
    if embedding_cluster:
        return embedding_cluster

    # Fallback to heuristic classification
    return _heuristic_classify(prompt)


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
