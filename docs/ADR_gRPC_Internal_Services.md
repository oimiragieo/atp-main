# ADR: gRPC for Internal Service Communication

## Status
Accepted

## Context
ATP has multiple internal services that need to communicate:
- Router ↔ Adapters (already implemented as gRPC services)
- Router ↔ Memory Gateway 
- Router ↔ Policy Engine (OPA)
- Future: Router ↔ Federation peers

Current state:
- Adapters expose gRPC `AdapterService` (Estimate/Stream/Health)
- Router calls adapters via HTTP in Rust implementation
- Python router service doesn't call adapters directly yet
- Memory gateway uses HTTP
- OPA policy checks use HTTP

## Decision
Use gRPC for all internal service communication where performance and type safety matter.

## Rationale
- **Type Safety**: Protobuf schemas prevent integration bugs
- **Performance**: Binary protocol faster than JSON/HTTP for frequent calls
- **Streaming**: Built-in support for streaming responses (adapter tokens)
- **Ecosystem**: ATP already has gRPC infrastructure (proto definitions, generated code)
- **Consistency**: Adapters already use gRPC, maintain uniformity

## Trade-offs
- **Complexity**: gRPC setup more complex than REST
- **Debugging**: Binary protocol harder to inspect than JSON
- **Dependencies**: Additional protobuf/gRPC libraries

## Implementation
1. Python router: Use grpcio + generated stubs for adapter calls
2. Memory gateway: Add gRPC service alongside HTTP
3. Keep HTTP for external APIs (REST for clients, gRPC internal)

## Migration Path
1. Add gRPC client to Python router for adapter calls
2. Add gRPC service to memory gateway
3. Update docker-compose to use gRPC URLs
4. Deprecate HTTP paths for internal calls

## Metrics
Track `internal_call_latency_ms{proto="grpc"}` for performance monitoring.
