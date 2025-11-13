Fragmentation & Reassembly (POC)

Summary
- Splits text payloads into fragments with flags and per-fragment checksum.
- Reassembles when final fragment arrives; validates contiguity and size consistency.
- Emits metrics and tracing for observability.

Semantics
- Non-final fragments include flag FRAG; final includes FRAG and LAST.
- Helper `to_more_flag_semantics` converts to MORE semantics (non-final have MORE; final omits MORE) for spec conformance tests.
- Duplicate fragments are ignored except re-processing LAST to attempt completion.
- Missing fragments after two completion attempts raise ValueError.
- Checksum: sha256 of text, truncated to 16 hex chars per fragment; reassembled payload gets checksum of full text in payload.

Observability
- Metric: `fragment_count_per_message` histogram with buckets [1, 2, 4, 8, 16, 32]. Recorded for any call to `fragment_frame`, including non-text payloads (count=1).
- Tracing: span `fragment.reassemble` records:
  - `frag.parts`: fragment count
  - `frag.session`, `frag.stream`, `frag.msg_seq`
  - `frag.bytes`: total bytes of reassembled text
 - Late fragments: counter `late_fragments_dropped` increments when a missing fragment arrives after the configured gap TTL (Reassembler `gap_ttl_s`).

Testing
- `tests/test_fragmentation.py` covers round-trip, missing fragment detection, duplicate handling, out-of-order handling, and checksum corruption.
- `tests/test_fragmentation_metrics.py` validates histogram increments for 1 and >1 fragments.
- `tests/test_fragmentation_tracing.py` validates the reassembly span and attributes using the dummy tracer.

Limitations (Next)
- Policy-driven max size, external buffers/GC and timers, binary payloads, cumulative/merkle checksums.
