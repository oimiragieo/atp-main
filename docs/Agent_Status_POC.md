Agent CTRL/STATUS (POC)

Summary
- Implements READY, BUSY, PAUSE, DRAINING agent states and computes effective window per session.
- Exposes a simple status event payload for broadcast.

Implementation
- router_service/control_status.py
  - Status enum covers READY, BUSY, PAUSE, DRAINING.
  - AgentStatus manager tracks status changes and increments `agent_status_changes_total`.
  - effective_window(session, router_allowed, suggested) returns:
    - READY: min(router_allowed, suggested or router_allowed)
    - BUSY: 0
    - PAUSE: router_allowed during grace_ms grace period, then 0 (honors `pauses_honored_total` counter)
    - DRAINING: at most 1
  - broadcast_status returns a simple event `{type: "agent.status", session, status}`.

Tests
- tests/test_agent_status_poc.py: verifies window logic, counter increments, and grace period expiration.

Future
- Wire into streaming loop to honor PAUSE grace windows and status broadcasts over SSE/WS.
