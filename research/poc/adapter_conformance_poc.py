import os
import sys
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from metrics.registry import REGISTRY


@dataclass
class AdapterBehavior:
    true_in_tokens: int
    true_out_tokens: int
    allowed_mape: float = 0.30  # 30%
    min_chunks: int = 2
    require_final: bool = True
    max_error_rate: float = 0.2
    max_p95_ms: float = 1500.0


@dataclass
class AdapterStub:
    estimate: dict[str, int]
    chunks: list[dict[str, Any]]
    health: dict[str, float]


def mape(est: int, truth: int) -> float:
    if truth <= 0:
        return 0.0
    return abs(est - truth) / truth


def conformance(adapter: AdapterStub, behavior: AdapterBehavior) -> dict[str, Any]:
    results: dict[str, Any] = {"pass": True, "failures": []}

    # Initialize metrics for GAP-119 (lazy initialization)
    adapter_estimate_mape_tokens = REGISTRY.histogram(
        "adapter_estimate_mape_tokens", [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    )
    adapter_estimate_mape_usd = REGISTRY.histogram(
        "adapter_estimate_mape_usd", [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    )

    # Estimate checks
    ein = adapter.estimate.get("in_tokens", -1)
    eout = adapter.estimate.get("out_tokens", -1)
    m_in = mape(ein, behavior.true_in_tokens)
    m_out = mape(eout, behavior.true_out_tokens)
    results["estimate_mape"] = {"in": m_in, "out": m_out}

    # Record MAPE metrics for GAP-119
    adapter_estimate_mape_tokens.observe(m_in)
    adapter_estimate_mape_tokens.observe(m_out)

    # For USD MAPE, use a default if not provided
    usd_est = adapter.estimate.get("usd_micros", 0)
    usd_true = 1000  # Placeholder true USD cost
    m_usd = mape(usd_est, usd_true)
    adapter_estimate_mape_usd.observe(m_usd)
    if any(v < 0 for v in [ein, eout]):
        results["pass"] = False
        results["failures"].append("estimate_missing")
    if m_in > behavior.allowed_mape or m_out > behavior.allowed_mape:
        results["pass"] = False
        results["failures"].append("estimate_mape_exceeded")

    # Stream checks
    chunk_count = len(adapter.chunks)
    has_final = any(c.get("type", "").endswith("final") and (not c.get("more", True)) for c in adapter.chunks)
    results["stream"] = {"chunks": chunk_count, "has_final": has_final}
    if chunk_count < behavior.min_chunks:
        results["pass"] = False
        results["failures"].append("too_few_chunks")
    if behavior.require_final and not has_final:
        results["pass"] = False
        results["failures"].append("missing_final")

    # Health checks
    p95 = float(adapter.health.get("p95_ms", 999999))
    err = float(adapter.health.get("error_rate", 1.0))
    health_ok = (p95 <= behavior.max_p95_ms) and (err <= behavior.max_error_rate)
    results["health"] = {"p95_ms": p95, "error_rate": err, "ok": health_ok}
    if not health_ok:
        results["pass"] = False
        results["failures"].append("health_slo_violation")

    return results


def predictability_score(estimates: list[tuple[int, int]], truths: list[tuple[int, int]]) -> float:
    """Return 1 - average MAPE across samples (clipped to [0,1])."""
    if not estimates or len(estimates) != len(truths):
        return 0.0
    total = 0.0
    for (ein, eout), (tin, tout) in zip(estimates, truths, strict=False):
        total += 0.5 * (mape(ein, tin) + mape(eout, tout))
    avg = total / len(estimates)
    return max(0.0, 1.0 - min(1.0, avg))
