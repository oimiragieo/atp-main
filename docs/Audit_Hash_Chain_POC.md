Audit Hash Chain (POC)

Summary
- Appends audit events to an append-only log with a cryptographic hash chain and HMAC tag to detect tampering.

Implementation
- memory-gateway/audit_log.py
  - append_event(path, event, secret, prev_hash_hex) => writes one JSON record with fields: event, prev, hash, hmac.
    - hash = SHA256(prev || canonical_json(event))
    - hmac = HMAC-SHA256(secret, hash)
  - verify_log(path, secret) => validates the entire log chain and HMACs.

Testing
- tests/test_audit_log.py: writes three events, verifies, then tampers with the file and expects verification to fail.

Operational Notes
- Keep secret material out of the repo; configure via environment/secret store.
- Rotate secrets by writing rotation markers and bridging chains (out of scope for this POC).
