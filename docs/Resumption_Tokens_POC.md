Resumption Tokens & Idempotency (POC)

Summary
- Provides short-lived tokens that allow a client to resume a stream once, supporting idempotent recovery after disconnects.

Implementation
- router_service/resumption.py: ResumptionTokenManager
  - issue(session, stream, ttl_s) -> token
  - resume(token, session, stream) -> bool (true if resume allowed; invalidates token)
  - purge_expired() for housekeeping
  - Metric: resumes_total increments on successful resume

Tests
- tests/test_resumption_tokens_poc.py covers successful resume, single-use behavior, and expiry.

Future
- Bind into the WS streaming path with a control frame for RESUME and correlation.
