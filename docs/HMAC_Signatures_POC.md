# HMAC Frame Signatures (POC)

Adds HMAC-SHA256 signatures over canonical JSON for ATP frames to enable tamper
detection at the transport boundary.

- Engine: `router_service/frame_sign.py`
- Tests: `tests/test_hmac_frame_sign_poc.py`
- Metrics: `frame_signature_fail_total`

Canonicalization
- JSON with sorted keys, compact separators, excluding the `sig` field.

Example
```
from router_service.frame_sign import sign_frame_dict, verify_frame_dict
sig = sign_frame_dict(frame_dict, key=b'secret')
frame_dict['sig'] = sig
assert verify_frame_dict(frame_dict, key=b'secret')
```

Integration (POC)
- An opt-in endpoint `/v1/verify_frame` verifies signatures when
  `ENABLE_FRAME_VERIFY=1` and `FRAME_VERIFY_SECRET` is set.
- For real deployments, bind to a KMS-backed key manager and perform verification
  on WS/ingress path.
