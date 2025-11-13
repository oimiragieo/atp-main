Heartbeat Scheduler (POC)

Summary
- Emits periodic heartbeats (HB) and signals FIN after an idle timeout.
- Provides counters and tracing spans for observability.

Behavior
- `HeartbeatScheduler(interval_s, idle_fin_s)` tracks last activity and last heartbeat.
- `tick(now)` returns events:
  - `HB` when `interval_s` elapsed since last heartbeat
  - `FIN` when `idle_fin_s` elapsed since last activity
- `note_activity(at)` resets the idle timer.

Observability
- Counter: `heartbeats_tx` increments on each HB.
- Spans:
  - `heartbeat.tx` with attributes `since_last_activity_s`, `interval_s`, `idle_fin_s`
  - `heartbeat.fin` with attributes `idle_duration_s`, `idle_fin_s`

Tests
- `tests/test_heartbeat_poc.py` validates cadence and FIN behavior.
- `tests/test_heartbeat_tracing_poc.py` validates tracing spans and attributes.
