# 14 — MCP Integration

This document explains how ATP can expose its routing & tool surfaces via the Model Context Protocol (MCP). For a non-jargon primer see `26_Client_Connection_Simplified.md`.

## Why MCP?
MCP standardizes how agents / IDEs discover tools and stream structured results. Instead of custom REST for every capability, a client can:
1. List available tools (capabilities) with schemas.
2. Invoke a tool generically (no bespoke endpoint glue).
3. Stream partial outputs (tokens, events) with consistent framing.
4. Subscribe to state changes (optional future extension).

## Scope Mapping
| ATP Concept | MCP Representation |
|-------------|--------------------|
| Adapter (model/tool) | Tool descriptor (name, description, input/output schemas) |
| Routing Request | `callTool` to a meta-tool (e.g., `route.complete`) |
| Partial Tokens | Streaming `toolOutput` events |
| Policy Denial | Error frame with policy code |
| Experiment Metadata | Extended fields in tool result annotations |

## Transport Options
- stdio (local dev; simplest)
- WebSocket (recommended for remote & streaming)
- HTTP/2 (future; multiplexing)

## Minimal Flow (WebSocket)
1. Client opens `wss://router.example.com/mcp`.
2. Sends `{"type":"listTools"}`.
3. Receives tools: `[ {"name":"route.complete", "inputSchema": {...}} ]`.
4. Sends `callTool` with input: `{ "prompt":"Explain RAG simply" }`.
5. Receives zero or more partial `toolOutput` frames.
6. Receives final `toolOutput` with `final=true` and metadata (latency, model_used, cost_estimate, savings_pct, policy_id_set).

## Tool Design Guidelines
| Principle | Rationale |
|-----------|-----------|
| Small, composable inputs | Encourages chaining & experimentation |
| Explicit cost/latency hints | Enables client-side budgeting |
| Structured error categories | Automated fallback & analytics |

## Example Tool Descriptor (Conceptual)
```json
{
	"name": "route.complete",
	"description": "Adaptive completion (cost/quality optimized)",
	"inputSchema": {
		"type": "object",
		"required": ["prompt"],
		"properties": {
			"prompt": {"type": "string"},
			"context_ids": {"type": "array", "items": {"type": "string"}},
			"max_tokens": {"type": "integer", "minimum": 1, "default": 512},
			"quality_target": {"type": "string", "enum": ["fast", "balanced", "high"]},
			"cost_ceiling_usd": {"type": "number"}
		}
	},
	"outputSchema": {
		"type": "object",
		"properties": {
			"text": {"type": "string"},
			"model_used": {"type": "string"},
			"latency_ms": {"type": "number"},
			"tokens": {"type": "integer"},
			"cost_usd": {"type": "number"},
			"savings_pct": {"type": "number"}
		}
	}
}
```

## Policy & Identity with MCP
- Auth still via Bearer token (initial handshake) or mTLS at transport.
- Tool invocation frames carry a `tenant` and optional `role` attribute; PDP enriches attributes server-side.
- Denials returned as structured error: `{ "error": { "code":"POLICY_DENY", "reason":"egress_block"}}`.

## Streaming Semantics
| Frame | Purpose |
|-------|---------|
| `toolOutput` (partial) | Incremental tokens / interim reasoning |
| `toolOutput` (final) | Final answer + metadata |
| `error` | Terminal failure |
| `heartbeat` | Liveness (optional) |

Partial frames SHOULD include `sequence` and MAY include cumulative token counts for client UI progress bars.

## Experiments via MCP
Experiment IDs (e.g., `exp_abc123`) and arm (`champion`/`challenger`) can be surfaced in output metadata enabling client-side analytics or safe-guard UIs.

## Differential Privacy & Telemetry
DP budgets are applied only to aggregated analytics exports—not real-time MCP responses. However, responses can include a field `dp_metrics_emitted: true|false` indicating if the interaction contributed to aggregate stats.

## Migration Path
1. Start with REST endpoints.
2. Introduce WebSocket for streaming tokens.
3. Add MCP endpoint exposing existing routing operations as standardized tools.
4. Gradually deprecate bespoke endpoints where MCP supersedes them.

## Open Questions
- Do we expose memory/context operations as separate tools or as implicit parameters?
- How to version tool schemas (proposal: semantic version in tool name suffix `route.complete.v1`).
- Should rejection sampling events (speculative inference) be surfaced to clients?

## Next Steps
- Define definitive JSON Schemas under `schemas/mcp/`.
- Implement adapter → tool descriptor generator.
- Build reference MCP client CLI for smoke tests.
