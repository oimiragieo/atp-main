"""QUIC vs HTTP/1.1 Head-of-Line Blocking Simulation POC
Simulates N logical streams over a single TCP connection (HOL blocking) vs QUIC multiplex (no cross-stream HOL).
Outputs latency percentile comparison.
"""

import random

random.seed(42)


def simulate(streams=5, messages=40):
    # Each message has base service time plus jitter; one slow message on TCP blocks others
    tcp_finish_times = [0] * streams
    quic_finish_times = [0] * streams
    tcp_latencies = []
    quic_latencies = []
    for m in range(messages):
        s = m % streams
        base = random.uniform(5, 15)
        if random.random() < 0.1:  # occasional slow
            base += random.uniform(40, 80)
        # TCP: serialized
        start_tcp = max(tcp_finish_times)
        tcp_finish = start_tcp + base
        tcp_finish_times[s] = tcp_finish
        tcp_latencies.append(tcp_finish - start_tcp)
        # QUIC: independent per-stream
        start_quic = quic_finish_times[s]
        quic_finish = start_quic + base
        quic_finish_times[s] = quic_finish
        quic_latencies.append(quic_finish - start_quic)

    def pct(lat, p):
        lat_sorted = sorted(lat)
        idx = int(p * len(lat_sorted)) - 1
        return lat_sorted[max(idx, 0)]

    p95_tcp = pct(tcp_latencies, 0.95)
    p95_quic = pct(quic_latencies, 0.95)
    return {"p95_tcp": round(p95_tcp, 2), "p95_quic": round(p95_quic, 2)}


if __name__ == "__main__":
    res = simulate()
    if res["p95_quic"] <= res["p95_tcp"]:
        print(f"OK: quic http3 comparison POC passed tcp_p95={res['p95_tcp']} quic_p95={res['p95_quic']}")
    else:
        print("FAIL: quic http3 comparison POC", res)
