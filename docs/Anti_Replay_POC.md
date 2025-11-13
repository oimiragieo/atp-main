# Anti‑Replay Nonces (POC)

Maintains a short‑lived nonce store to reject duplicate messages and reduce
replay risk at the transport boundary.

- Engine: `router_service/replay_guard.py`
- Tests: `tests/test_replay_guard_poc.py`
- Metrics: `replay_reject_total`

Usage (POC)
- Nonce value supplied by caller is checked at ingress against an in‑memory
  store with TTL and capacity.
- Duplicate nonces seen within TTL are rejected and counted.

Example
```
from router_service.replay_guard import NonceStore
store = NonceStore(ttl_s=60, cap=10000)
assert store.check_and_store('nonce-123')  # first time ok
assert store.check_and_store('nonce-123') is False  # duplicate rejected
```

Integration
- The `/v1/verify_frame` endpoint can enable nonce checks with
  `ENABLE_REPLAY_GUARD=1`. Frames should include a top‑level `nonce` string.
- For production, use a Redis‑backed implementation instead of in‑memory.
