STRIDE Threat Modeling (POC)

Summary
- Automates a basic STRIDE matrix from an architecture YAML with components and dataflows.

Usage
- Input: data/threat_model_poc.yaml (components, trust_boundaries, dataflows)
- Tool: tools/stride_threat_model_poc.py
- Test: tests/test_stride_threat_model_poc.py

Heuristics
- Components exposed to the internet (or listening on well-known ports) are flagged for Spoofing, Tampering, and DoS.
- Components that store data are flagged for Information Disclosure (and Tampering risk).
- Components without auth are flagged for Spoofing; admin components for Elevation of Privilege.
- Dataflows from internet → component add Spoofing, Tampering, Information Disclosure, and DoS for the destination.
- Internal flows to unauthenticated destinations add Repudiation.

Limitations
- High-level heuristic only; not a substitute for expert review.
- Future: per-dataflow auth/encryption flags, trust boundary IDs, and mitigation mapping.
