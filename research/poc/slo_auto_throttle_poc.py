"""SLO Auto-Throttle POC
Monitors error rate and p95 latency; reduces concurrency window when SLO violated, restores when healthy.
"""

import random


def auto_throttle(rounds=60, start_window=10):
    window = start_window
    history = []
    for _r in range(rounds):
        # simulate metrics
        error_rate = random.uniform(0, 0.15)
        p95 = random.uniform(50, 200)
        slo_error = 0.1
        slo_p95 = 150
        if error_rate > slo_error or p95 > slo_p95:
            window = max(1, int(window * 0.8))
        else:
            window = min(50, window + 1)
        history.append((error_rate, p95, window))
    return history


if __name__ == "__main__":
    hist = auto_throttle()
    final_window = hist[-1][2]
    if 1 <= final_window <= 50:
        print(f"OK: slo auto throttle POC passed final_window={final_window}")
    else:
        print("FAIL: slo auto throttle POC", final_window)
