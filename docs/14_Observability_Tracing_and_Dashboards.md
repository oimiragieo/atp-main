# 14 — Observability, Tracing & Dashboards

- OpenTelemetry traces (ingress → dispatch → fanout → adapter → consensus) to Tempo.
- Prometheus metrics: windows/estimates/consensus & per-adapter MAPE.
- Grafana: Starter, Windows & Consensus, Adapter Predictability dashboards.
- Logging SLOs and redaction policy for PII/secrets.

Spans & Attributes (POC)
- fair.acquire: fair.fast_path (bool), window.allowed (int)
- aimd.feedback: aimd.session, aimd.before, aimd.after, aimd.latency_ms, aimd.ok
- window.update: window.before, window.after, window.delta
- ack.update: ack.session, ack.stream, ack.msg_seq, ack.frag_seq, ack.ack_up_to, ack.nacks_count, ack.completed, ack.proc_ms
- fragment.reassemble: frag.parts, frag.session, frag.stream, frag.msg_seq, frag.bytes
- bandit.select: bandit.strategy, bandit.cluster, bandit.candidates, bandit.choice

Span Hierarchy (POC)
- dispatch (parent)
  - adapter.stream (child)
  - ack.update (child)
  - window.update (child)

Metrics (selected)
- agreement_pct histogram (consensus)
- budget_remaining_usd_micros gauge (budget)
- heartbeats_tx counter (heartbeat)
- adapter_estimate_mape_tokens / adapter_estimate_mape_usd histograms (adapter predictability)
- cost_usd_total_qos_<qos> counters (cost by QoS)

Trace Sampling (POC)
- Configure per-QoS ratios via env `ROUTER_SAMPLING_QOS`, e.g., `gold:1.0,silver:0.5,bronze:0.1`.
- Use helper `start_sampled_span(name, qos)` to respect sampling in code paths.
