"""POC: Consensus scoring (GAP-024), multi-strategy consensus (GAP-100), and disagreement heatmap (GAP-101).

Provides Jaccard agreement, multi-strategy reducers, and disagreement visualization.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from metrics.registry import REGISTRY

_H_AGREEMENT = REGISTRY.histogram("agreement_pct", [0.2, 0.4, 0.6, 0.8, 0.9])


def jaccard_agreement(texts: list[str]) -> float:
    if not texts:
        return 0.0
    sets = [set(t.lower().split()) for t in texts]
    inter = set.intersection(*sets) if len(sets) > 1 else sets[0]
    union = set.union(*sets) if len(sets) > 1 else sets[0]
    score = 0.0 if not union else len(inter) / len(union)
    try:
        _H_AGREEMENT.observe(score)
    except Exception:  # noqa: S110
        pass
    return score


def meets_threshold(texts: list[str], threshold: float = 0.7) -> bool:
    return jaccard_agreement(texts) >= threshold


class Strategy(str, Enum):
    UNION = "union"
    QUORUM = "quorum"
    TWO_PHASE = "two_phase"


_CTR_UNION = REGISTRY.counter("consensus_strategy_used_union_total")
_CTR_QUORUM = REGISTRY.counter("consensus_strategy_used_quorum_total")
_CTR_TWO_PHASE = REGISTRY.counter("consensus_strategy_used_two_phase_total")


def _tokens(s: str) -> set[str]:
    return set(s.lower().split())


def consensus_union(texts: list[str]) -> str:
    """Union of tokens across texts (simple whitespace tokens)."""
    _CTR_UNION.inc(1)
    uni: set[str] = set()
    for t in texts:
        uni |= _tokens(t)
    return " ".join(sorted(uni))


def consensus_quorum(texts: list[str], quorum: int = 2) -> str | None:
    """Return a text that appears at least `quorum` times (exact match)."""
    _CTR_QUORUM.inc(1)
    counts: dict[str, int] = {}
    for t in texts:
        counts[t] = counts.get(t, 0) + 1
    for t, c in counts.items():
        if c >= max(1, int(quorum)):
            return t
    return None


def consensus_two_phase(texts: list[str], agree_threshold: float = 0.6) -> str | None:
    """Two-phase: pick a representative then require agreement threshold.

    Phase 1: pick the text with highest average Jaccard to others.
    Phase 2: if average agreement >= threshold, return it; else None.
    """
    _CTR_TWO_PHASE.inc(1)
    if not texts:
        return None
    best_idx = 0
    best_score = -1.0
    tok = [_tokens(t) for t in texts]
    for i in range(len(texts)):
        sc = 0.0
        for j in range(len(texts)):
            if i == j:
                continue
            inter = len(tok[i] & tok[j])
            union = len(tok[i] | tok[j]) or 1
            sc += inter / union
        avg = sc / max(1, len(texts) - 1)
        if avg > best_score:
            best_score = avg
            best_idx = i
    return texts[best_idx] if best_score >= agree_threshold else None


# ---- Disagreement Heatmap (GAP-101) ----

_H_DISAGREEMENT_REGIONS = REGISTRY.histogram("disagreement_regions_avg", [1, 2, 3, 5, 10])


def disagreement_heatmap(texts: list[str]) -> list[dict[str, Any]]:
    """Compute disagreement regions across texts using token-level diff.

    Returns a list of disagreement spans with positions and conflicting tokens.
    Each span represents a region where texts differ significantly.
    """
    if len(texts) < 2:
        return []

    # Tokenize all texts
    tokenized = [_tokens(t) for t in texts]
    token_lists = [t.lower().split() for t in texts]

    # Find common tokens across all texts
    # (Not currently used but kept for future enhancements)
    if tokenized:
        set.intersection(*tokenized)

    # Find disagreement regions by comparing token sequences
    regions = []
    max_len = max(len(tl) for tl in token_lists)

    for pos in range(max_len):
        tokens_at_pos = []
        for tl in token_lists:
            if pos < len(tl):
                tokens_at_pos.append(tl[pos].lower())
            else:
                tokens_at_pos.append(None)

        # Check if there's disagreement at this position
        unique_tokens = {t for t in tokens_at_pos if t is not None}
        if len(unique_tokens) > 1 and len(unique_tokens) < len(texts):  # Partial disagreement
            regions.append(
                {
                    "position": pos,
                    "conflicting_tokens": list(unique_tokens),
                    "frequency": {token: tokens_at_pos.count(token) for token in unique_tokens if token},
                    "span_type": "token_disagreement",
                }
            )

    # Also check for missing tokens (gaps)
    for _i, tl in enumerate(token_lists):
        if len(tl) < max_len:
            regions.append(
                {
                    "position": len(tl),
                    "conflicting_tokens": ["<END>"] + [tl[-1] if tl else "<EMPTY>" for tl in token_lists],
                    "frequency": {"<GAP>": 1},
                    "span_type": "length_disagreement",
                }
            )

    # Record metrics
    try:
        _H_DISAGREEMENT_REGIONS.observe(len(regions))
    except Exception:  # noqa: S110
        pass

    return regions


def highlight_disagreements(text: str, regions: list[dict[str, Any]]) -> str:
    """Highlight disagreement regions in text with markup.

    Returns text with disagreement spans wrapped in [DISAGREEMENT:... ] markers.
    """
    if not regions:
        return text

    tokens = text.split()
    result = []
    highlighted_positions = {r["position"] for r in regions}

    for i, token in enumerate(tokens):
        if i in highlighted_positions:
            region = next(r for r in regions if r["position"] == i)
            conflicting = ", ".join(region["conflicting_tokens"][:3])  # Limit to 3 for readability
            result.append(f"[DISAGREEMENT:{conflicting}] {token}")
        else:
            result.append(token)

    return " ".join(result)
