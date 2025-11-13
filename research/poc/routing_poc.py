from dataclasses import dataclass


@dataclass
class Candidate:
    name: str
    ctx: int  # context tokens
    est_in: int
    est_out: int
    usd_micros: int
    p95_ms: int
    confidence: float  # 0..1


def select_adapters(
    cands: list[Candidate],
    k: int,
    required_ctx: int,
    budget_usd_micros: int,
    w_conf: float = 0.7,
    w_cost: float = 0.2,
    w_lat: float = 0.1,
) -> list[Candidate]:
    """Pick up to k adapters by score with simple constraints.

    Score = w_conf*confidence - w_cost*norm_cost - w_lat*norm_latency
    """
    # filter by context and budget
    feasible = [c for c in cands if c.ctx >= required_ctx and c.usd_micros <= budget_usd_micros]
    if not feasible:
        return []
    max_cost = max(c.usd_micros for c in feasible) or 1
    max_lat = max(c.p95_ms for c in feasible) or 1

    def score(c: Candidate) -> float:
        nc = c.usd_micros / max_cost
        nl = c.p95_ms / max_lat
        return w_conf * c.confidence - w_cost * nc - w_lat * nl

    ranked = sorted(feasible, key=score, reverse=True)
    sel: list[Candidate] = []
    spent = 0
    for r in ranked:
        if len(sel) >= k:
            break
        if spent + r.usd_micros <= budget_usd_micros:
            sel.append(r)
            spent += r.usd_micros
    return sel
