"""Verifier Judge Consensus POC
Applies a secondary judge scoring to candidate answers and checks consistency threshold.
"""

import logging
import random

# Configure logging for POC
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def judge(answer: str):
    # simple heuristic: length and presence of capital letter
    return (1 if any(c.isupper() for c in answer) else 0) + min(len(answer) / 20, 1)


def consensus(candidates):
    scored = [(c, judge(c) + random.uniform(-0.05, 0.05)) for c in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[0]
    second = scored[1]
    gap = top[1] - second[1]
    return {"winner": top[0], "gap": round(gap, 3), "confidence": round(top[1], 3)}


if __name__ == "__main__":
    res = consensus(["Answer One", "answer two", "Another Option"])
    if res["gap"] >= 0 and res["winner"] in ["Answer One", "Another Option"]:
        logger.info(f"OK: verifier judge consensus POC passed winner={res['winner']} gap={res['gap']}")
    else:
        logger.error(f"FAIL: verifier judge consensus POC {res}")
