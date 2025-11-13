"""POC: Per-adapter predictability metrics (GAP-066).

Computes MAPE for tokens and USD and records histograms per adapter.
"""

from __future__ import annotations

from metrics.registry import REGISTRY

_H_MAPE_TOK = REGISTRY.histogram("adapter_estimate_mape_tokens", [0.05, 0.1, 0.2, 0.3, 0.5, 1.0])
_H_MAPE_USD = REGISTRY.histogram("adapter_estimate_mape_usd", [0.05, 0.1, 0.2, 0.3, 0.5, 1.0])
_CTR_UNDER_TOK = REGISTRY.counter("router_estimate_under_rate_tokens_total")
_CTR_UNDER_USD = REGISTRY.counter("router_estimate_under_rate_usd_total")


def _mape(pred: float, obs: float) -> float:
    if pred <= 0:
        return 0.0 if obs == 0 else 1.0
    return abs(obs - pred) / pred


def record_predictability(
    adapter: str, pred_tokens: int, obs_tokens: int, pred_usd_micros: int, obs_usd_micros: int
) -> None:
    mt = _mape(float(pred_tokens), float(obs_tokens))
    mu = _mape(float(pred_usd_micros), float(obs_usd_micros))
    # Observe into histograms; adapter label omitted in POC registry, but aggregate histograms are present.
    _H_MAPE_TOK.observe(mt)
    _H_MAPE_USD.observe(mu)
    if obs_tokens > pred_tokens:
        _CTR_UNDER_TOK.inc(1)
    if obs_usd_micros > pred_usd_micros:
        _CTR_UNDER_USD.inc(1)
