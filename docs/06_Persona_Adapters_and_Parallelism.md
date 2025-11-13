Purpose

This document defines how the ATP Router interacts with Persona Adapters and supports Parallel Thinking. It extends the ATP and AGP specifications to handle role-based personas, compliance-bound personas, and multi-clone inference for reliability and performance.

1. Persona Adapters
1.1 Definition

A Persona Adapter is a containerized unit representing a specific role, expertise, or behavioral configuration of an LLM or agent. Examples include:

doctor-advisor

network-engineer

compliance-lawyer

creative-writer

Each persona adapter encapsulates prompt engineering, tool access, and policy constraints for its domain.

1.2 Standard Container Layout

System Prompt File: /persona/system_prompt.txt

Persona Config: /persona/config.yaml

role: human-readable identifier

tools: list of allowed tool IDs

qos_tier: latency/reliability class

compliance: policy flags (e.g., PII_filter, HIPAA_guard)

Adapter Entrypoint: /persona/adapter.py implementing the Estimate, Stream, and Health APIs.

1.3 Lifecycle States

Persona adapters cycle through well-defined states:

READY: available for routing

BUSY: currently executing tasks

PAUSE: temporarily unavailable (e.g., under backpressure)

DRAINING: finishing active requests before shutdown

1.4 Security & Permissions

Policies enforced via Open Policy Agent (OPA).

Tool access is gated per persona, ensuring least-privilege principles.

SPIFFE/SPIRE handles service identity and mTLS for adapter-to-router communication.

2. Parallelism & Parallel Thinking
2.1 Motivation

Tasks often benefit from simultaneous perspectives (e.g., medical + legal + ethical). Parallel execution enables multiple persona adapters to contribute insights concurrently.

2.2 Modes of Parallel Execution

Speculative Parallelism: Multiple adapters attempt the same task, router reconciles fastest/highest-quality result.

Diverse Parallelism: Distinct personas run in parallel, router merges their outputs into a composite response.

Clone Parallelism: Multiple instances of the same persona run with varied seeds to reduce variance and detect hallucinations.

2.3 Router Responsibilities

Launch persona clones in parallel.

Buffer and sequence outputs, similar to TCP windowing.

Apply reconciliation strategies:

First-Win (low latency)

Consensus (majority agreement)

Weighted Merge (using AGP policy weights)

3. Policy & Governance
3.1 Compliance Personas

Certain adapters are designated compliance filters (e.g., HIPAA persona). All sensitive traffic can be routed through them before external transmission.

3.2 Policy DSL Integration

Persona configs declare compliance flags. Router consults OPA for per-task enforcement. Example:

role: compliance-lawyer
tools: [document_redactor]
qos_tier: high_reliability
compliance: [PII_filter, GDPR_guard]

4. Observability

Each persona logs telemetry via OpenTelemetry.

Parallel sessions are tagged with a session_id and persona_id for tracing.

Aggregated metrics: task latency, error rate, agreement ratio across clones.

5. Example Flow

Client submits request tagged as medical + compliance.

Router dispatches to:

doctor-advisor (2 parallel clones)

compliance-lawyer (filter layer)

Router buffers responses, ensures ordering, reconciles outputs.

Composite answer returned to client with audit trail.

6. Future Work

Adaptive routing weights via contextual bandits (Vowpal Wabbit).

Persona reputation scoring based on historical accuracy and reliability.

Cross-router persona federation (AGP extension).