import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.routing_poc import Candidate, select_adapters


def main():
    cands = [
        Candidate("cheap-fast", ctx=32000, est_in=2000, est_out=500, usd_micros=10000, p95_ms=300, confidence=0.62),
        Candidate(
            "expensive-strong", ctx=1000000, est_in=2000, est_out=500, usd_micros=300000, p95_ms=900, confidence=0.88
        ),
        Candidate("mid", ctx=128000, est_in=2000, est_out=500, usd_micros=80000, p95_ms=600, confidence=0.75),
    ]
    # Case 1: small required ctx and tight budget → pick cheap-fast
    sel = select_adapters(cands, k=1, required_ctx=8000, budget_usd_micros=20000)
    assert len(sel) == 1 and sel[0].name == "cheap-fast"

    # Case 2: allow 2 picks and higher budget → cheap-fast + mid (confidence & cost balance)
    sel = select_adapters(cands, k=2, required_ctx=8000, budget_usd_micros=100000)
    names = [s.name for s in sel]
    assert names == ["cheap-fast", "mid"]

    # Case 3: high ctx requirement excludes cheap-fast and mid; expensive-strong within budget
    sel = select_adapters(cands, k=1, required_ctx=200000, budget_usd_micros=400000)
    assert len(sel) == 1 and sel[0].name == "expensive-strong"

    print("OK: routing selection POC passed")


if __name__ == "__main__":
    main()
