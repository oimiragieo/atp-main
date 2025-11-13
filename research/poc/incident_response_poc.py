"""Incident response runbooks & drills POC.
Models runbook steps, can execute a simulated drill capturing timings and success/fail.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class Step:
    name: str
    action: str


@dataclass
class RunResult:
    step: str
    success: bool
    duration_ms: float


class Runbook:
    def __init__(self, name: str, steps: list[Step]):
        self.name = name
        self.steps = steps

    def drill(self) -> list[RunResult]:
        results: list[RunResult] = []
        for s in self.steps:
            t0 = time.time()
            # simulate action time
            time.sleep(0.01)
            success = True
            results.append(RunResult(s.name, success, (time.time() - t0) * 1000))
        return results


if __name__ == "__main__":
    rb = Runbook(
        "security-incident",
        [Step("detect", "query SIEM"), Step("contain", "block adapter"), Step("recover", "restore state")],
    )
    res = rb.drill()
    assert len(res) == 3 and all(r.success for r in res)
    print("OK: incident response runbooks POC passed; steps=", len(res))
