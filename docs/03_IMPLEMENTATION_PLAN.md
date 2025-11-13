Phase 1: Reference Router MVP

Implement ATP frame codec (JSON v1.1) with the new control/status and tool frames.

Add Redis state + WAL append for rehydration and crash recovery.

Build 2 adapters:

Ollama/Qwen local (summarizer).

Gemini or GPT-5 remote (reviewer).

Consensus Engine v1:

Canonicalizer + lexical + embedding hybrid scorer.

Provisional consensus support with expiry timers.

Backpressure handler: honor BUSY/PAUSE from agents.

Expose metrics + traces via OTel.

👉 At this stage: a single-node router that can handle code-review fan-out with provisional consensus.

🌍 Phase 2: Distributed & Federated

Add sharding via rendezvous hashing.

Inter-router AGP protocol with ROUTE_UPDATE (federated metrics exchange).

Circuit breakers, AIMD congestion control across shards.

Formalize QoS tiers (gold/silver/bronze) with enforcement.

👉 This turns one router into a mesh—scalable across regions, with policy-driven agent federation.

🛡️ Phase 3: Security & Governance

mTLS/OIDC for router ↔ agent auth.

Enforce tool_permissions + security_groups at routing layer.

Signed usage summaries for billing integrity.

Immutable audit logs for consensus decisions (tamper-evident).

📢 Phase 4: Standardization

Publish ATP spec as OAT-WG RFC v1.0.

Build SDKs (Python, TS, Go) with conformance tests.

Run interop demos:

LangChain agents behind ATP.

Qwen-Agent ↔ Autogen interoperability via ATP frames.

Invite ecosystem players (Anthropic, OpenAI, HuggingFace) to contribute adapters.