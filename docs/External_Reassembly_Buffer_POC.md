External Reassembly Buffer (POC)

Summary
- Provides an external buffer API to persist fragment parts across process boundaries and complete reassembly when all parts arrive.

Implementation
- router_service/reassembly_store.py: ExternalReassemblyStore
  - push_part(session, stream, msg_seq, frag_seq, text, is_last) stores the fragment and returns (complete, full_text_if_complete).
  - clear removes state for a key; TTL pruning removes stale entries.
  - Metric: buffer_store_ops increments on push/clear.
- router_service/fragmentation.py
  - Reassembler accepts an optional store; if provided, delegates persistence and completes via the store.

Tests
- tests/test_external_reassembly_store_poc.py simulates reassembly across instances using a shared store.

Future
- Redis/SQL backend implementation and backpressure-aware buffer sizing.
