import time
from collections.abc import Callable


def run_load(op: Callable[[], None], n: int = 50) -> tuple[float, float, float]:
    """Run op n times, return (p50_ms, p95_ms, rps)."""
    lats: list[float] = []
    t_start = time.time()
    for _ in range(n):
        t0 = time.time()
        op()
        lats.append((time.time() - t0) * 1000.0)
    dur = time.time() - t_start
    lats.sort()

    def pct(p):
        if not lats:
            return 0.0
        idx = min(len(lats) - 1, int(p * len(lats)) - 1)
        return lats[idx]

    p50 = pct(0.5)
    p95 = pct(0.95)
    rps = n / max(dur, 1e-9)
    return p50, p95, rps
