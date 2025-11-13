# SPIFFE/SPIRE SVID (POC)

This POC stubs out SVID fetching and rotation for the router process to
illustrate the integration seam with SPIRE Workload API.

- Engine: `router_service/spiffe_svid.py`
- Tests: `tests/test_spiffe_svid_poc.py`
- Metrics: `svid_rotation_total` increments when a refresh occurs.

Model
- `SVID`: holds `spiffe_id`, `cert_pem`, `key_pem`, and `expires_at` timestamp.
- `SpireClientStub`: fetches/rotates SVIDs and exposes `rotate_if_needed(min_ttl_s)`.

Example
```
from router_service.spiffe_svid import SpireClientStub
client = SpireClientStub('router')
svid = client.fetch_svid(ttl_s=300)
if not svid.is_valid():
    svid = client.rotate_if_needed(min_ttl_s=60)
```

Next
- Replace stub with real SPIRE Workload API calls.
- Bind mTLS contexts using the SVID cert/key for inbound/outbound traffic.
