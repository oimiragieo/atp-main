# 10 — Memory & Context Fabric

A shared, low-latency memory fabric to enrich agents:
- Namespaces (tenant/project/session) and TTLs.
- KV + Vector store facade with write-through cache; pluggable backends (Redis/PG/Weaviate).
- Consistency levels: EVENTUAL (default) and READ_YOUR_WRITES for same-session flows.
- Access control via OPA; row-level encryption for sensitive scopes.
- API contracts for put/get/search; ingestion policies and schema evolution.
