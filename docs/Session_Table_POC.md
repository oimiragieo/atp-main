Persistent Session Table (POC)

Summary
- Provides a simple file-backed session table to simulate externalizing session/window state (e.g., Redis/SQL).

Implementation
- router_service/session_table.py: SessionTableFile
  - upsert(session, attrs) inserts or updates a session record with timestamp and attributes.
  - get(session), delete(session), count(), purge_expired(ttl_s).
  - Persists to JSON file and maintains metric `sessions_active` gauge.

Tests
- tests/test_session_table_poc.py exercises persistence across restarts and TTL purge.

Future
- Replace with Redis/SQL backends and add schema migration/versioning.
