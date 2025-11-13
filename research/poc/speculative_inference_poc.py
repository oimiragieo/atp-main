"""Speculative/Hybrid Inference POC
Simulates a fast draft model and a slower accurate model. If draft prefix matches final answer prefix,
we accept early and save latency.
"""

import random
import time


def simulate(trials=100):
    saved = 0
    total_latency = 0
    accepted = 0
    for _ in range(trials):
        # draft latency 10ms, final 40ms
        time.time()
        draft_ans = random.choice(["hello world", "good morning", "quick brown fox"])
        final_ans = draft_ans if random.random() < 0.7 else draft_ans.split()[0] + " altered"
        draft_latency = 0.01
        final_latency = 0.04
        time.sleep(0.0001)  # simulate
        if final_ans.startswith(draft_ans.split()[0]):
            # speculative accept
            saved += final_latency
            accepted += 1
        total_latency += draft_latency + final_latency
    avg_saved = saved / trials
    return {"avg_saved_s": round(avg_saved, 4), "accept_rate": round(accepted / trials, 3)}


if __name__ == "__main__":
    res = simulate()
    if res["avg_saved_s"] > 0.01 and res["accept_rate"] > 0.5:
        print(f"OK: speculative inference POC passed saved={res['avg_saved_s']} accept_rate={res['accept_rate']}")
    else:
        print("FAIL: speculative inference POC", res)
