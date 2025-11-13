# Error Taxonomy (POC)

The router exposes structured error codes to clients and increments per-code metrics.

- Mapping implemented in `router_service/error_mapping.py`.
- Metrics counters: `error_code_<code>_total`.
- Tests: `tests/test_error_mapping_poc.py`.

Codes
- `prompt_too_large`: Input exceeds configured limits.
- `no_models_available`: No eligible models after policy/health filtering.
- `rate_limited`: Client exceeded allowed request rate/burst.
- `request_cancelled`: Request cancelled by client or server.
- `backpressure`: Request refused due to flow control or resource pressure.
- `internal_error`: Unhandled failure path.

Example payload
```
{"error": "rate_limited", "detail": "burst"}
```

Rollout guidance
- Log errors with correlation IDs.
- Export counters to Prometheus/Grafana with alerts on sustained `internal_error` rate.
- Ensure PII is not leaked in `detail`.
