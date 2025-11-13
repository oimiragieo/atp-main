Unified Circuit Breakers (POC)

Summary
- Implements a simple circuit breaker with trip/reset logic and an open-circuit gauge.

Implementation
- router_service/circuit_breaker.py
  - CircuitBreaker(fail_threshold, reset_timeout_s, half_open_successes)
  - allow_request() gates calls based on state; record_failure()/record_success() update state.
  - Metric: circuits_open gauge reflects number of open circuits.

Tests
- tests/test_circuit_breaker_poc.py covers trip on threshold, half-open probe, and reset after successes.

Future
- Consolidate adapters and external dependencies under a BreakerManager with per-endpoint breakers.
