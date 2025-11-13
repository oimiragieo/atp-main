"""Soak Test POC
Simulates sustained load over a duration collecting latency samples, error rate, throughput.
Outputs an OK line with p95 and RPS if SLO thresholds met.
"""

import random
import statistics
import time


def run_soak(duration_s=1.5, target_rps=120):
    interval = 1 / target_rps
    latencies = []
    errors = 0
    count = 0
    start = time.time()
    next_tick = start
    while time.time() - start < duration_s:
        now = time.time()
        if now < next_tick:
            time.sleep(next_tick - now)
        time.time()
        # simulate variable latency and occasional errors
        base = random.uniform(5, 30)
        # 5% slow
        if random.random() < 0.05:
            base += random.uniform(30, 80)
        # 2% error
        if random.random() < 0.02:
            errors += 1
        else:
            # simulate work
            time.sleep(base / 1000.0)
            latencies.append(base)
        count += 1
        next_tick += interval
    duration = time.time() - start
    success = count - errors
    rps = success / duration if duration > 0 else 0
    p95 = statistics.quantiles(latencies, n=100)[94] if latencies else 0
    return {
        "count": count,
        "errors": errors,
        "rps": round(rps, 2),
        "p95_ms": round(p95, 2),
        "error_rate": round(errors / max(count, 1), 4),
    }


if __name__ == "__main__":
    res = run_soak()
    if res["rps"] > 30 and res["p95_ms"] < 120 and res["error_rate"] < 0.2:
        print(f"OK: soak test POC passed rps={res['rps']} p95={res['p95_ms']}ms err_rate={res['error_rate']}")
    else:
        print("FAIL: soak test POC", res)
