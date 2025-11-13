from dataclasses import dataclass


@dataclass
class Window:
    max_parallel: int
    max_tokens: int
    max_usd_micros: int


@dataclass
class Usage:
    inflight: int
    tokens: int
    usd: int


def compute_window_update(prev: Usage, curr: Usage, base: Window, delta_pct: int = 20) -> Window | None:
    """If usage changed more than delta_pct of capacity, adjust window down or up (AIMD-ish)."""

    def pct(cap, used):
        return (used * 100) // max(1, cap)

    p_prev, p_curr = pct(base.max_parallel, prev.inflight), pct(base.max_parallel, curr.inflight)
    t_prev, t_curr = pct(base.max_tokens, prev.tokens), pct(base.max_tokens, curr.tokens)
    u_prev, u_curr = pct(base.max_usd_micros, prev.usd), pct(base.max_usd_micros, curr.usd)

    if any(abs(b - a) >= delta_pct for a, b in [(p_prev, p_curr), (t_prev, t_curr), (u_prev, u_curr)]):
        # simplistic rule: if growing, decrease 10%; if shrinking, increase 10% (bounded)
        factor = 0.9 if (p_curr > p_prev or t_curr > t_prev or u_curr > u_prev) else 1.1

        def adj(x):
            return max(1, int(x * factor))

        return Window(adj(base.max_parallel), adj(base.max_tokens), adj(base.max_usd_micros))
    return None
