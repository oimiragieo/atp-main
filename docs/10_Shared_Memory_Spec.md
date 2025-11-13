
# 10 — Shared Memory Fabric (SMF) — Concise POC
- Purpose: shared, low-latency memory for plans/findings/artifacts.
- T0 KV: memory-gateway (POC FastAPI). T1 Vector/T2 Graph/T3 Artifacts omitted in POC.
- APIs (POC):
  - PUT /v1/memory/{ns}/{key} {object}
  - GET /v1/memory/{ns}/{key}
  - POST /v1/memory/search {q}
- Security: add OPA + mTLS in production; this POC is local only.
