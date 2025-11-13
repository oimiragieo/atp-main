from collections import deque
from dataclasses import dataclass


@dataclass
class ProbeResult:
    ok: bool
    p95_ms: float
    error_rate: float


class HealthGate:
    def __init__(self, window: int = 5, max_p95_ms: float = 1500.0, max_error_rate: float = 0.2):
        self.window = window
        self.max_p95 = max_p95_ms
        self.max_err = max_error_rate
        self.hist: dict[str, deque[ProbeResult]] = {}

    def record(self, name: str, result: ProbeResult) -> None:
        dq = self.hist.setdefault(name, deque(maxlen=self.window))
        dq.append(result)

    def ready(self, name: str) -> bool:
        dq = self.hist.get(name)
        if not dq or len(dq) < max(1, self.window // 2):
            return False  # require minimal history
        avg_p95 = sum(r.p95_ms for r in dq) / len(dq)
        avg_err = sum(1.0 - (1.0 if r.ok else 0.0) for r in dq) / len(dq)
        return (avg_p95 <= self.max_p95) and (avg_err <= self.max_err)
