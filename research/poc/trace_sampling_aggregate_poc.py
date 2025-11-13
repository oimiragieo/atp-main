"""Trace sampling aggregate wrapper POC.
Wraps multiple sampling strategies and selects one per request context; attaches exemplar when sampled.
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.trace_sampling_poc import AlwaysOn, ParentBased, RateLimiting, exemplar


class SamplerRouter:
    def __init__(self):
        self.always = AlwaysOn()
        self.rate = RateLimiting(5.0)
        self.parent = ParentBased(root=self.always)

    def decide(self, parent_sampled=None, priority=False):
        # priority requests use AlwaysOn, else rate limiting with parent-based fallback
        if priority:
            sampled = self.always.should_sample()
            strat = "always"
        elif parent_sampled is not None:
            sampled = self.parent.should_sample(parent_sampled=parent_sampled)
            strat = "parent"
        else:
            sampled = self.rate.should_sample()
            strat = "rate"
        ex = (
            exemplar(f"trace-{random.randint(1000, 9999)}", random.random() * 100, {"strategy": strat})
            if sampled
            else None
        )
        return {"sampled": sampled, "strategy": strat, "exemplar": ex}


if __name__ == "__main__":
    r = SamplerRouter()
    a = r.decide(priority=True)
    b = r.decide(parent_sampled=True)
    c = r.decide()
    assert a["sampled"] and a["strategy"] == "always"
    assert b["strategy"] == "parent"
    # c may or may not sample but structure must exist
    assert "sampled" in c and "strategy" in c
    print("OK: trace sampling aggregate POC passed")
