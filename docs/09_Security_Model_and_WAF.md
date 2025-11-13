# 09 — Security Model & WAF

This document defines the security posture across the ATP/AGP stack:
- Zero-trust identity (SPIFFE/SPIRE), mTLS everywhere, and short-lived SVIDs.
- Web Application Firewall (WAF) layer: OWASP Core Rules baseline + prompt-injection signatures.
- Input hardening pipeline: MIME sniffing, schema validation, max sizes, allowlists.
- Secret egress guard: detects and blocks leaking keys/tokens/PII; emits audit events.
- Rate limiting & DDoS protections: token-bucket per tenant/QoS; circuit breakers.
- Policy-as-code with OPA for tool permissions and data_scope checks.
- Threat modeling (STRIDE) and Security Incident Response playbooks.

## SPIFFE/SPIRE SVID (POC)

Router obtains a SPIFFE Verifiable Identity Document (SVID) from a SPIRE agent
and uses it to bind mTLS. This POC includes a stubbed client and model with
rotation and a rotation metric.

- Engine: `router_service/spiffe_svid.py`
- Test: `tests/test_spiffe_svid_poc.py`
- Metric: `svid_rotation_total`.

## Frame Signatures (POC)

To detect tampering at the transport boundary, frames carry an HMAC-SHA256
signature over a canonical JSON form (sorted keys, compact, excluding the `sig`
field). Verification occurs at ingress.

- Engine: `router_service/frame_sign.py`
- Verify endpoint: `/v1/verify_frame` (POC) with `ENABLE_FRAME_VERIFY=1` and
  `FRAME_VERIFY_SECRET` or key manager (see below).
- Key management (POC): `router_service/key_manager.py`; enable via
  `ENABLE_KMS=1` and seed keys with `KEYMGR_KEYS="k1=alpha,k2=beta"`.
- Metrics: `frame_signature_fail_total`.

## Anti‑Replay Nonces (POC)

Ingress enforces a short‑lived nonce store to reject duplicate messages and
reduce replay risk.

- Engine: `router_service/replay_guard.py` (in‑memory; substitute Redis for prod).
- Enable with `ENABLE_REPLAY_GUARD=1`; frames should include a top‑level `nonce`.
- Metrics: `replay_reject_total`.

## Data‑Scope Enforcement (POC)

Restricts access based on declared data scope.

- Enable with `ENABLE_SCOPE_ENFORCE=1` and allowlist scopes via
  `ALLOWED_DATA_SCOPES="public,teamA"`.
- Requests must include header `x-data-scope`; forbidden scopes return 403 and
  increment `scope_violation_total`.

## OIDC/JWT Auth (POC)

Ingress can enforce OIDC/JWT Bearer tokens on `/v1/ask`.

- Engine: `router_service/oidc.py` (HS256 sign/verify helpers)
- Enable with `ENABLE_OIDC=1`
- Config:
  - `OIDC_SECRET` (shared secret for HS256)
  - `OIDC_ISS` (expected issuer) and `OIDC_AUD` (expected audience)
- Metrics: `oidc_invalid_total` increments for invalid/expired/mismatched tokens
- Test: `tests/test_oidc_auth_poc.py`

JWKS caching (POC)
- Enable with `ENABLE_OIDC_JWKS=1` and provide `JWKS_JSON` or `JWKS_PATH`.
- Optional `JWKS_TTL_S` controls cache TTL (default 300s). File changes (mtime) are detected for reloads.

## mTLS Context From SVID (POC)

Build mTLS contexts using the SVID material. The POC provides context builders
as a seam to bind real PEMs in future work.

- Engine: `router_service/mtls_context.py`
- Builders: `build_server_context_from_svid`, `build_client_context_from_svid`
- Metric: `mtls_context_build_success_total` (and `mtls_context_build_fail_total` on failures)
- Test: `tests/test_mtls_context_poc.py`

## WAF Core Rules (POC)

Blocks obvious prompt‑injection attempts at ingress.

- Engine: `router_service/waf.py`
- Enable with `ENABLE_WAF=1` (applies to `/v1/ask`)
- Metric: `waf_block_total` increments on block
- Test: `tests/test_waf_poc.py`

Custom rules (POC)
- Provide `WAF_PATTERNS` as a JSON list or comma‑separated patterns; they are applied before built‑in rules.

## Input Hardening (POC)

Validates incoming payloads prior to dispatch.

- Engine: `router_service/input_hardening.py`
- MIME sniffing: distinguishes `text/plain` vs `application/octet-stream` using a simple heuristic.
- Schema validation: checks presence of required top‑level keys.
- Metric: `input_reject_total` increments on invalid MIME or schema failures.
- Tests: `tests/test_input_hardening_poc.py`.

## Log Redaction Policy (POC)

Redacts sensitive data (PII/secrets) from logs and objects.

- Engine: `memory-gateway/pii.py` provides `redact_text` and `redact_object`.
- Metric: `redactions_total` increments per redaction (text matches and key redactions).
- Tests: `tests/test_log_redaction_policy_poc.py`.

## Secret Egress Guard (POC)

Detects likely secrets in outbound content and blocks egress.

- Engine: `router_service/secret_guard.py` with basic detector repository (AWS keys, JWT/OAuth tokens, OpenAI keys, GCP SA JSON markers).
- Metric: `secret_block_total` increments on detection.
- Tests: `tests/test_secret_guard_poc.py`.
- ## Signed Route Updates (POC)

Route update diffs (RIB) are signed to ensure integrity and authenticity when
propagating changes.

- Engine: `router_service/rib_sign.py` (HMAC-SHA256 over canonical JSON).
- Metric: `route_sig_fail_total` increments on signature mismatch.
- Test: `tests/test_rib_sign_poc.py`.
