This document visualizes the router’s control flow for parallel sessions (multi-persona/multi-clone) and per-lane (single persona/clone) execution. It includes both ASCII and Graphviz DOT diagrams, with events, guards, and actions.

1) Concepts & Notation

Session: one client task fan-out; contains N lanes (personas and/or clones).

Lane: a single routed call to an adapter (persona or clone of a premium reviewer).

Events (➜): incoming signals (adapter frames, timeouts, policy decisions).

Guards ([…]): boolean conditions checked on transitions.

Actions ({…}): side effects performed during a transition.

## Common events:

DISPATCH_OK, DISPATCH_ERR

PARTIAL, FINAL, FAIL

QUORUM_REACHED, DEADLINE, EARLY_EXIT

BACKPRESSURE, RESUME

CANCEL_LANES

ESCALATE (spawn premium lane per policy)

## Common guards:

[budget_ok], [window_ok], [policy_ok]

[agree ≥ τ], [provisional_enabled], [arbiter_allowed]

## Common actions:

{emit_provisional}, {emit_final}, {shrink_window}, {cancel_bronze}

{route_to_arbiter}, {update_consensus}, {reallocate_budget}

2) Session FSM (ASCII)
+---------+         +-------------+         +------------+         +--------------+
|  INIT   | --(fan)→| DISPATCHED  | --(rx)→ | STREAMING  | --(buf)→|  BUFFERING   |
+----+----+         +------+------+         +-----+------+         +------+-------+
     |                     |                        |                      |
     | DISPATCH_ERR        | DISPATCH_OK            | PARTIAL              | update consensus
     v                     v                        |                      v
  [error]-------------+  spawn lanes                |                  +-----------+
                      |                              | FINAL/FAIL       |RECONCILING|
                      |                              v                  +-----+-----+
                      |                         +----+-----+                 |
                      |                         | QUORUM? | yes              |
                      |                         +----+-----+                 |
                      |                              |                       |
                      |      [provisional_enabled]   |                       |
                      |             yes              | no                    |
                      |                              |                       |
                      |                        +-----v-----+        +--------v--------+
                      |                        | PROVISIONAL|        |  DEADLINE/     |
                      |                        |   EMIT     |        |  ESCALATION    |
                      |                        +-----+-----+        +--------+--------+
                      |                              |                        |
                      |               EARLY_EXIT/    |                        |
                      |               CANCEL_LANES   |                        |
                      |                              v                        v
                      |                         +----+-----+           +-----+------+
                      |                         | COMPLETE |<----------|  ARBITER   |
                      |                         +----------+           +------------+


Notes

STREAMING/BUFFERING run concurrently as lanes deliver PARTIAL chunks.

On [agree ≥ τ] (quorum), optionally {emit_provisional} and proceed while remaining lanes run.

EARLY_EXIT can {cancel_bronze} lanes and finalize early.

DEADLINE/ESCALATION may {route_to_arbiter} if consensus is insufficient.

3) Lane FSM (ASCII) — per persona/clone
+------+     +-----------+      +-----------+      +-----------+      +-----------+
| INIT | --> | ADMITTED  | -->  | STREAMING | -->  | FINALIZED |      |  FAILED   |
+--+---+     +-----+-----+      +-----+-----+      +-----+-----+      +-----+-----+
   |               |                  |                  ^                  ^
   | [!budget_ok]  | DISPATCH_OK      | PARTIAL          | FINAL            | error/timeout
   | or !policy_ok v                  |                  |                  |
   +------------->(REJECTED)----------+------------------+------------------+
                      |
                      | backpressure / PAUSE
                      v
                   (PAUSED) --RESUME--> STREAMING


Notes

ADMITTED only if [budget_ok ∧ window_ok ∧ policy_ok].

PAUSED on adapter backpressure; router shrinks effective window until RESUME.

FAILED triggers session-level reconciliation without this lane’s contribution.

4) Graphviz DOT — Session FSM

Copy into a .dot file and render with dot -Tpng session.dot -o session.png

digraph SessionFSM {
  rankdir=LR;
  node [shape=rect, style=rounded];

  INIT [label="INIT"];
  DISPATCHED [label="DISPATCHED"];
  STREAMING [label="STREAMING"];
  BUFFERING [label="BUFFERING"];
  PROVISIONAL [label="PROVISIONAL EMIT"];
  RECONCILING [label="RECONCILING"];
  ARBITER [label="ARBITER"];
  COMPLETE [label="COMPLETE", shape=doubleoctagon];
  ERROR [label="ERROR", shape=octagon];
  DEADLINE [label="DEADLINE / ESCALATION"];

  INIT -> DISPATCHED [label="fan-out lanes\n{allocate lanes}"];
  DISPATCHED -> ERROR [label="DISPATCH_ERR"];
  DISPATCHED -> STREAMING [label="DISPATCH_OK"];

  STREAMING -> BUFFERING [label="PARTIAL/FINAL"];
  BUFFERING -> PROVISIONAL [label="[agree ≥ τ ∧ provisional_enabled]\n{emit_provisional}"];
  BUFFERING -> RECONCILING [label="[agree ≥ τ] or FINAL aggregation"];
  BUFFERING -> DEADLINE [label="DEADLINE or low confidence\n{escalate?}"];

  PROVISIONAL -> RECONCILING [label="EARLY_EXIT or quorum finalize\n{cancel bronze}"];

  DEADLINE -> ARBITER [label="[arbiter_allowed]\n{route_to_arbiter}"];
  DEADLINE -> RECONCILING [label="no arbiter"];

  ARBITER -> RECONCILING [label="arbiter_result"];

  RECONCILING -> COMPLETE [label="{emit_final}"];

  {rank=same; STREAMING; BUFFERING;}
}

5) Graphviz DOT — Lane FSM
digraph LaneFSM {
  rankdir=LR;
  node [shape=rect, style=rounded];

  INIT [label="INIT"];
  ADMITTED [label="ADMITTED"];
  STREAMING [label="STREAMING"];
  PAUSED [label="PAUSED"];
  FINALIZED [label="FINALIZED", shape=doubleoctagon];
  FAILED [label="FAILED", shape=octagon];
  REJECTED [label="REJECTED", shape=octagon];

  INIT -> REJECTED [label="![budget_ok ∧ window_ok ∧ policy_ok]"];
  INIT -> ADMITTED [label="[budget_ok ∧ window_ok ∧ policy_ok]"];

  ADMITTED -> STREAMING [label="DISPATCH_OK"];
  ADMITTED -> FAILED [label="DISPATCH_ERR"];

  STREAMING -> PAUSED [label="BACKPRESSURE / PAUSE\n{shrink_window}"];
  PAUSED -> STREAMING [label="RESUME"];

  STREAMING -> STREAMING [label="PARTIAL\n{update_consensus}"];
  STREAMING -> FINALIZED [label="FINAL"];
  STREAMING -> FAILED [label="FAIL / TIMEOUT"];

  REJECTED -> FAILED [style=dashed, label="(no-op for session)"];
}

6) Transition Table (abridged)
From → To	Event / Guard	Actions
INIT → DISPATCHED	fan-out	{allocate lanes}
DISPATCHED → ERROR	DISPATCH_ERR	{log, rollback budget}
DISPATCHED → STREAMING	DISPATCH_OK	{start timers}
STREAMING → BUFFERING	PARTIAL/FINAL	{reassemble, update_consensus}
BUFFERING → PROVISIONAL	[agree ≥ τ ∧ provisional_enabled]	{emit_provisional}
BUFFERING → RECONCILING	QUORUM_REACHED ∨ all lanes FINAL	{freeze inputs}
BUFFERING → DEADLINE	DEADLINE ∨ low_confidence	{escalate?}
DEADLINE → ARBITER	[arbiter_allowed]	{route_to_arbiter}
ARBITER → RECONCILING	arbiter_result	{merge}
RECONCILING → COMPLETE	—	{emit_final, cancel_remaining}
7) Implementation Notes

Sequencing: per-lane msg_seq/frag_seq must be monotonic; buffer gaps with a small timer; drop/mark late fragments past expiry.

Provisional: include expiry_ms; if later consensus falls below threshold, emit a revision frame.

Early-Exit: when provisional confidence passes a higher threshold, cancel low-priority lanes ({cancel_bronze}) and reallocate budget to lagging premium lanes if needed.

Backpressure: honor adapter control.status=BUSY|PAUSE|DRAINING and compute **effective window = min(router_window, agent_suggested_window)`.

Observability: tag spans with session_id, lane_id, persona_id, diversity_seed; keep Prometheus labels low-cardinality.

8) Files & Cross-Refs

Extends: 01_ATP.md (frames, windows), 02_v0.2 Addendum & Clarifications.md (provisional consensus, backpressure)

Complements: 04_AGP_Federation_Spec.md (federation), 06_Persona_Adapters_and_Parallelism.md (personas & clones)

Implementation: 05_Phase01_mvp.md, 03_IMPLEMENTATION_PLAN.md

9) Parallel Session State Machine (GAP-110)

The Parallel Session State Machine implements basic multi-persona orchestration with reconciliation policies. This is a simplified version focused on core parallel execution without provisional emissions or arbitration.

### ASCII Diagram
```
+-------+     +------------+     +-----------+     +------------+     +-------------+     +----------+
| INIT  | --> | DISPATCHED | --> | STREAMING | --> | BUFFERING | --> | RECONCILING | --> | COMPLETE |
+-------+     +------------+     +-----------+     +------------+     +-------------+     +----------+
    |                |                |                |                |                |
    |   add_persona  |  dispatch_err  |   buffer_data  |   all_complete |   reconcile   |   terminal
    |                |                |   mark_complete|                |               |
    v                v                v                v                v                |
 (error)         (error)         (error)         (error)         (error)              (done)
```

### States
- **INIT**: Session created, personas can be added
- **DISPATCHED**: RPCs sent to adapter personas
- **STREAMING**: Adapters streaming token responses
- **BUFFERING**: Router aggregating responses, waiting for all personas to complete
- **RECONCILING**: Applying reconciliation policy (First-Win, Consensus, Weighted-Merge)
- **COMPLETE**: Final result returned to client

### Transitions
- INIT → DISPATCHED: When session dispatch begins
- DISPATCHED → STREAMING: When first adapter response received
- STREAMING → BUFFERING: When all personas marked as complete
- BUFFERING → RECONCILING: When buffering complete
- RECONCILING → COMPLETE: When reconciliation policy applied

### Reconciliation Policies
- **First-Win**: Return result from first completed persona
- **Consensus**: Currently delegates to First-Win (placeholder for future consensus logic)
- **Weighted-Merge**: Combine results from all personas with weighting

### Implementation
Located in: `router_service/agp_update_handler.py`
- `ParallelSessionState` enum
- `ParallelSession` class with state management
- `ParallelSessionManager` for lifecycle management
- Comprehensive test suite in `tests/test_agp_update_handler.py`