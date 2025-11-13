ACK/NACK Strategy (POC)

Goals
- Provide reliable fragment delivery signals using a hybrid approach:
  - Piggyback ACKs: implicit acknowledgements via contiguous progress (ack_up_to) to minimize overhead.
  - Explicit NACKs: enumerate gaps only once the final fragment index is known (after last seen) to drive retransmission.

Semantics
- ack_up_to is the highest contiguous fragment index from 0 that has been observed. It is monotonic per (session, stream, msg_seq).
- Before the last fragment is observed, no NACKs are emitted to avoid premature retransmits.
- After the last fragment is observed, NACKs list all missing indices < expected_last, and may be repeated until gaps are filled.
- Completion occurs once all fragments [0..expected_last] have arrived; state is discarded.

Metrics & Tracing
- Counters:
  - acks_tx: increments each time ack_up_to advances (each contiguous step is one increment).
  - retransmit_requests: increments by the number of missing indices when emitting NACKs.
- Span `ack.update` (dummy tracer or OTEL): attributes include session/stream/msg_seq, current frag_seq, ack_up_to, nacks_count, completed, proc_ms.

Reference
- Engine: router_service/ack_logic.py (not yet wired into service path; PoC-level).
- Tests: tests/test_ack_logic_poc.py, tests/test_ack_logic_metrics_poc.py, tests/test_ack_tracing_poc.py, tests/test_ack_conformance.py

Future
- Backpressure-aware ACK window sizing and integration with QoS scheduler.
- Retransmission rate limiting and jitter to avoid bursts.
- ERROR mapping for ESEQ_RETRY frames and a retransmit queue with TTL de-dup are provided as PoC in `router_service/errors.py` (ESEQ_RETRY) and `router_service/retransmit.py`.
