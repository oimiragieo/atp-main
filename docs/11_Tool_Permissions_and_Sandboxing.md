# 11 — Tool Permissions & Sandboxing

- Tool descriptors declare capabilities & cost model.
- Least-privilege grants in `meta.tool_permissions` gated by OPA.
- Sandboxed execution (gVisor/Firecracker) for high-risk tools.
- Egress policies (DNS/IP/Domain allowlists), FS ACLs, network namespaces.
- Cost caps per tool; usage attribution in audit logs.
