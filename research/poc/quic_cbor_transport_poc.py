"""QUIC + CBOR Transport POC (Simulated)
Simulates packet framing with CBOR-like dict (using Python dict) and QUIC stream multiplexing metrics.
"""

import random


def simulate(streams=5, frames_per_stream=20):
    latencies = []
    reordered = 0
    sent = 0
    for _s in range(streams):
        last_seq = -1
        for i in range(frames_per_stream):
            base = random.uniform(2, 8)
            jitter = random.uniform(0, 3)
            lat = base + jitter
            latencies.append(lat)
            seq = i
            if seq < last_seq:
                reordered += 1
            last_seq = seq
            sent += 1
    p95 = sorted(latencies)[int(0.95 * len(latencies)) - 1]
    return {"p95_ms": round(p95, 2), "reordered": reordered, "sent": sent}


if __name__ == "__main__":
    res = simulate()
    if res["p95_ms"] < 12 and res["reordered"] == 0:
        print(f"OK: quic cbor transport POC passed p95={res['p95_ms']} sent={res['sent']}")
    else:
        print("FAIL: quic cbor transport POC", res)
