# Client Connection (Plain-English Guide)

Goal: Explain how an app ("client") actually talks to the platform. No jargon first, then details.

## 1. The Super Simple Mental Model
Think of ATP as a smart traffic cop sitting in front of different AI models and tools.

You (the client) send ONE request to ATP. ATP:
1. Cleans & checks it (auth, redaction, policy).
2. Decides which model(s) or tool chain to try.
3. Maybe runs several in parallel (speculative) or tests a new one quietly (champion/challenger).
4. Streams results back to you.
5. Logs cost, latency, policy, privacy usage.

So instead of your app calling Model A, B, C directly, you call ATP once.

## 2. Connection Options (Good, Better, Best)
| Option | When to Use | What It Is |
|--------|-------------|------------|
| REST HTTPS | Easiest | Simple POST JSON → get JSON/stream back |
| WebSocket | Need streaming tokens or multi-turn | Persistent bidirectional channel |
| MCP (Model Context Protocol) | Integrate with agent frameworks/tools | A standardized protocol so IDEs/agents can discover & use ATP tools |

## 3. Do I Have to Use MCP? (No)
MCP is OPTIONAL. It just standardizes discovery ("what tools/models exist?"), invocation, and streaming. If you ignore MCP you can still hit plain HTTPS or WebSocket endpoints.

## 4. What MCP Adds (If You Use It)
Without MCP: You hardcode endpoints like `/v1/complete`.
With MCP: Your agent asks ATP: "list tools" → gets a schema back. Then it invokes a tool via a generic channel. This reduces custom glue when swapping models/tools.

## 5. Typical Non-MCP Flow (REST)
1. Your backend (or frontend) sends POST `/v1/route` with: prompt, context IDs, tenant, desired quality/cost hints.
2. ATP validates auth token → redacts PII → policy check.
3. Routing engine chooses model plan (maybe: cheap model first; escalate if confidence low).
4. Adapter(s) invoked; result aggregated.
5. Response JSON: `{id, output, latency_ms, model_used, cost_estimate}`.
6. Your code renders output.

## 6. Typical Streaming Flow (WebSocket)
1. Open `wss://router.example.com/ws`.
2. Send an initial JSON frame: session info + your prompt.
3. Receive partial frames as ATP relays or merges model outputs.
4. Close when you get an `END` flag.

The existing `client/ws_client_stub.py` is a primitive version of this.

## 7. Typical MCP Flow (Conceptual)
1. Start an MCP client runtime (e.g., inside an agent host or IDE extension).
2. It connects to ATP MCP endpoint (could be a local socket, HTTP upgrade, or stdio for local dev).
3. Client sends `listTools` → ATP returns tool descriptors (name, input schema, output schema).
4. Client sends `callTool` with structured params → ATP executes through routing/policy → streams back results.
5. Observability + cost accounting happen transparently.

## 8. Minimal Code Examples (Pseudo)
REST (Python):
```python
import requests
resp = requests.post('https://router/api/v1/route', json={'prompt':'Explain RAG like I am 10','tenant':'acme'})
print(resp.json()['output'])
```

WebSocket (JS):
```js
const ws = new WebSocket('wss://router/ws');
ws.onopen = () => ws.send(JSON.stringify({type:'SYN', prompt:'hello'}));
ws.onmessage = e => console.log('chunk', e.data);
```

MCP (Pseudo):
```jsonc
// listTools request
{"type":"listTools"}
// response
{"tools":[{"name":"complete","inputSchema":{...}}]}
// callTool
{"type":"callTool","name":"complete","args":{"prompt":"Hello"}}
```

## 9. Auth Simplified
| Layer | Purpose | Example |
|-------|---------|---------|
| API Key / OAuth Token | Identify tenant/user | `Authorization: Bearer <token>` |
| (Future) mTLS | Service-to-service trust inside network | SPIFFE IDs |
| Policy Attributes | Decide what is allowed | tenant=acme role=analyst region=us-east |

## 10. Where Privacy Fits
Redaction happens BEFORE routing so no raw PII is sent to external models. Differential privacy applies to aggregate analytics metrics (not your live response).

## 11. Error Handling (Simple Mental Model)
| Error Type | You See | Meaning |
|------------|---------|---------|
| 401 | Auth failed | Bad/missing token |
| 403 | Policy deny | Not allowed (tool/model/region) |
| 429 | Throttled | Rate/Quota exceeded or backpressure |
| 5xx | Internal | Retry with jitter; ATP may auto failover |

## 12. Local Dev vs Prod
| Local | Prod |
|-------|------|
| `docker compose up` single box | Multi-region k8s |
| No auth or simple token | OIDC + mTLS + policy PDP |
| In-memory state | Postgres/Redis/vector DB |
| Basic logs | Full OTEL traces & metrics |

## 13. Deciding Which Client Type to Use
| Need | Choose |
|------|--------|
| Quick backend integration | REST |
| Token streaming / interactive agent | WebSocket |
| Tool discovery & standard agent interoperability | MCP |

You can mix: e.g., use REST for simple completions + MCP for advanced tool orchestration.

## 14. Migration Path (If You Already Call Models Directly)
1. Wrap existing model calls behind a simple interface.
2. Redirect that interface to ATP REST endpoint.
3. Enable policy & logging (observe metrics durability).
4. Introduce routing experiments (bandit, champion/challenger).
5. Switch streaming or MCP where beneficial.

## 15. Quick Recap
Send one request to ATP instead of many to providers. ATP handles: auth → clean → decide → run → stream → account → audit. MCP is optional sugar for standardized tool discovery. Start with REST; evolve to WebSocket or MCP as complexity grows.

---
Questions not covered? Add them to `24_FAQ_and_Glossary.md`.
