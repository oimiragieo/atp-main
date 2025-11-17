# Security Testing Checklist for ATP Platform

**Version:** 1.0
**Last Updated:** 2025-11-17
**Status:** Ready for Security Testing

---

## Overview

This checklist provides a systematic approach to security testing for the ATP platform, covering OWASP Top 10 vulnerabilities, authentication, authorization, and platform-specific security concerns.

## Pre-Testing Setup

### Environment Preparation
- [ ] Deploy ATP in isolated testing environment
- [ ] Configure test API keys separate from production
- [ ] Enable all security features (ROUTER_REQUIRE_AUTH=1)
- [ ] Set up security testing tools (OWASP ZAP, Burp Suite)
- [ ] Configure logging aggregation for security events

### Test Data Preparation
- [ ] Create test user accounts with different permission levels
- [ ] Prepare malicious payload datasets
- [ ] Set up network traffic capture

---

## OWASP Top 10 (2021) Testing

### A01:2021 - Broken Access Control

**Authentication Tests:**
- [ ] Verify unauthenticated requests to protected endpoints return 401
- [ ] Test authentication bypass attempts (manipulated headers, tokens)
- [ ] Verify API key validation is constant-time (timing attack prevention)
- [ ] Test oversized API keys (DoS prevention - should reject >512 chars)
- [ ] Verify public endpoints (/healthz, /metrics, /docs) accessible without auth

**Authorization Tests:**
- [ ] Test horizontal privilege escalation (access other users' data)
- [ ] Test vertical privilege escalation (access admin functions)
- [ ] Verify tenant isolation in multi-tenant scenarios
- [ ] Test session/token expiration

**Test Commands:**
```bash
# Unauthenticated access
curl -X POST http://localhost:7443/v1/ask -d '{"prompt":"test"}'
# Expected: 401 Unauthorized

# Invalid API key
curl -X POST http://localhost:7443/v1/ask \
  -H "X-API-Key: invalid-key" \
  -d '{"prompt":"test"}'
# Expected: 401 Invalid API key

# Valid API key
curl -X POST http://localhost:7443/v1/ask \
  -H "X-API-Key: $ROUTER_ADMIN_API_KEY" \
  -d '{"prompt":"test"}'
# Expected: 200 OK

# Public endpoint without auth
curl http://localhost:7443/healthz
# Expected: 200 OK
```

---

### A02:2021 - Cryptographic Failures

**Encryption Tests:**
- [ ] Verify API keys use constant-time comparison (secrets.compare_digest)
- [ ] Test for hardcoded secrets in codebase (`grep -r "api.*key.*=" --include="*.py"`)
- [ ] Verify sensitive data not logged (check logs for API keys, PII)
- [ ] Test TLS/SSL configuration (if deployed with HTTPS)
- [ ] Verify no sensitive data in error messages

**Test Commands:**
```bash
# Check for hardcoded secrets
rg -i "password|api.?key|secret" --type py | grep -v "# " | grep "="

# Check logs for sensitive data leakage
docker compose logs router | grep -i "api.?key\|password\|secret"
```

---

### A03:2021 - Injection

**SQL Injection Tests:**
- [ ] Test parameterized queries in adaptive_stats.py
- [ ] Verify no dynamic SQL construction with user input
- [ ] Test special characters in all input fields: `' OR '1'='1`, `"; DROP TABLE--`

**Command Injection Tests:**
- [ ] Verify bash tool is disabled by default (ROUTER_ENABLE_BASH_TOOL=0)
- [ ] Test dangerous command blocking: `rm -rf /`, `dd if=/dev/zero`, `sudo su`
- [ ] Test eval/exec pattern blocking
- [ ] Test null byte injection: `command\x00malicious`
- [ ] Test fork bomb detection: `:(){ :|:& };:`

**Input Validation Tests:**
- [ ] Test prompt length limits (should reject >100,000 chars)
- [ ] Test quality parameter with invalid values (should only accept fast/balanced/high)
- [ ] Test max_cost_usd with negative/oversized values
- [ ] Test latency_slo_ms with negative/oversized values

**Test Commands:**
```bash
# SQL injection attempt (should be safe due to parameterized queries)
# This is testing the validation, not actual SQL injection
curl -X POST http://localhost:7443/v1/ask \
  -H "X-API-Key: $ROUTER_ADMIN_API_KEY" \
  -d '{"prompt":"test' OR '1'='1", "quality":"fast"}'

# Command injection via bash tool (should be disabled)
curl -X POST http://localhost:7443/tools/bash \
  -H "X-API-Key: $ROUTER_ADMIN_API_KEY" \
  -d '{"command":"rm -rf /"}'
# Expected: Error: Bash tool is disabled OR Command blocked

# Oversized prompt (DoS attempt)
python3 -c "print('a' * 200000)" | curl -X POST http://localhost:7443/v1/ask \
  -H "X-API-Key: $ROUTER_ADMIN_API_KEY" \
  -d @-
# Expected: 422 Validation error or 400 Bad request

# Invalid quality value
curl -X POST http://localhost:7443/v1/ask \
  -H "X-API-Key: $ROUTER_ADMIN_API_KEY" \
  -d '{"prompt":"test", "quality":"super-fast-extreme"}'
# Expected: 422 Validation error
```

---

### A04:2021 - Insecure Design

**Architecture Review:**
- [ ] Verify security controls exist at multiple layers (defense-in-depth)
- [ ] Review threat model against current implementation
- [ ] Verify rate limiting is configured
- [ ] Test concurrent request limits (ROUTER_MAX_CONCURRENT=200)
- [ ] Verify circuit breaker patterns for external services

---

### A05:2021 - Security Misconfiguration

**Configuration Tests:**
- [ ] Verify ROUTER_ADMIN_API_KEY is required and validated (≥32 chars)
- [ ] Test with missing ROUTER_ADMIN_API_KEY (should fail to start)
- [ ] Verify authentication disabled by default for development
- [ ] Verify bash tool disabled by default
- [ ] Check CORS configuration (should only allow GET, POST, OPTIONS)
- [ ] Verify debug mode disabled in production
- [ ] Test error messages don't leak sensitive information

**Test Commands:**
```bash
# Test missing API key
unset ROUTER_ADMIN_API_KEY
python3 router_service/service.py
# Expected: ValueError: ROUTER_ADMIN_API_KEY environment variable must be set

# Test CORS restrictions
curl -X PUT http://localhost:7443/v1/ask \
  -H "Origin: http://evil.com" \
  -H "X-API-Key: $ROUTER_ADMIN_API_KEY"
# Expected: 405 Method Not Allowed (PUT not in allow_methods)

# Test DELETE method (should be blocked)
curl -X DELETE http://localhost:7443/v1/ask \
  -H "X-API-Key: $ROUTER_ADMIN_API_KEY"
# Expected: 405 Method Not Allowed
```

---

### A06:2021 - Vulnerable and Outdated Components

**Dependency Tests:**
- [ ] Run `pip list --outdated` to check for outdated packages
- [ ] Scan dependencies for known vulnerabilities: `safety check`
- [ ] Verify no deprecated Python packages
- [ ] Check Docker base images for vulnerabilities: `docker scan`

**Test Commands:**
```bash
# Check outdated packages
pip list --outdated

# Security vulnerability scan
pip install safety
safety check --json

# Check for security advisories
pip-audit
```

---

### A07:2021 - Identification and Authentication Failures

**Authentication Mechanism Tests:**
- [ ] Test brute force protection (rate limiting on failed auth attempts)
- [ ] Verify weak passwords rejected (if password auth added later)
- [ ] Test session fixation attacks
- [ ] Verify secure session management
- [ ] Test concurrent session limits

**Password/Key Tests:**
- [ ] Test minimum API key length enforcement (≥32 chars)
- [ ] Verify constant-time comparison prevents timing attacks
- [ ] Test key rotation procedures

---

### A08:2021 - Software and Data Integrity Failures

**Code Integrity:**
- [ ] Verify all dependencies pinned to specific versions
- [ ] Test CI/CD pipeline security
- [ ] Verify code signing (if implemented)
- [ ] Test update mechanisms are secure

---

### A09:2021 - Security Logging and Monitoring Failures

**Logging Tests:**
- [ ] Verify authentication failures are logged
- [ ] Verify no sensitive data in logs (API keys, passwords, PII)
- [ ] Test log injection attacks: `test\nINFO Fake log entry`
- [ ] Verify structured logging format
- [ ] Test log aggregation and alerting

**Test Commands:**
```bash
# Generate auth failure and check logs
curl -X POST http://localhost:7443/v1/ask \
  -H "X-API-Key: wrong-key" \
  -d '{"prompt":"test"}'

docker compose logs router | grep -i "authentication failed"
# Expected: Log entry with failure details but no full API key

# Check for sensitive data leakage
docker compose logs router | grep -i "api.?key\|password\|secret" | grep -v "redacted\|masked\|***"
# Expected: No matches
```

---

### A10:2021 - Server-Side Request Forgery (SSRF)

**SSRF Tests:**
- [ ] Test URL validation in any URL-accepting endpoints
- [ ] Verify internal network access restrictions
- [ ] Test metadata service access (169.254.169.254)
- [ ] Verify DNS rebinding protection

---

## ATP-Specific Security Tests

### Bash Tool Security

**Command Validation:**
- [ ] Test dangerous command blocking (comprehensive list)
- [ ] Test command length limits (>10000 chars)
- [ ] Test null byte injection
- [ ] Test privilege escalation attempts
- [ ] Verify disabled by default

**Test Commands:**
```bash
# Enable bash tool for testing
export ROUTER_ENABLE_BASH_TOOL=1

# Test dangerous commands (all should be blocked)
curl -X POST http://localhost:7443/tools/bash \
  -H "X-API-Key: $ROUTER_ADMIN_API_KEY" \
  -d '{"command":"rm -rf /"}'

curl -X POST http://localhost:7443/tools/bash \
  -H "X-API-Key: $ROUTER_ADMIN_API_KEY" \
  -d '{"command":"dd if=/dev/zero of=/dev/sda"}'

curl -X POST http://localhost:7443/tools/bash \
  -H "X-API-Key: $ROUTER_ADMIN_API_KEY" \
  -d '{"command":"sudo su"}'

curl -X POST http://localhost:7443/tools/bash \
  -H "X-API-Key: $ROUTER_ADMIN_API_KEY" \
  -d '{"command":"eval '\''echo pwned'\''"}'

curl -X POST http://localhost:7443/tools/bash \
  -H "X-API-Key: $ROUTER_ADMIN_API_KEY" \
  -d '{"command":":(){ :|:& };:"}'

# All above should return: "Command blocked for security reasons"
```

### Input Validation

**Prompt Validation:**
- [ ] Test maximum prompt length (100,000 chars)
- [ ] Test minimum prompt length (1 char)
- [ ] Test Unicode and special characters
- [ ] Test control characters

**Parameter Validation:**
- [ ] Test quality values (only fast/balanced/high allowed)
- [ ] Test max_cost_usd range (0-100)
- [ ] Test latency_slo_ms range (0-300000)
- [ ] Test negative values (should be rejected)

---

## Performance & DoS Testing

### Rate Limiting
- [ ] Test RPS limits (ROUTER_RPS_LIMIT)
- [ ] Test burst handling (ROUTER_RPS_BURST)
- [ ] Test concurrent connection limits
- [ ] Verify graceful degradation under load

### Resource Exhaustion
- [ ] Test memory limits with large requests
- [ ] Test CPU limits with complex operations
- [ ] Test connection pool exhaustion
- [ ] Test disk space exhaustion (logs, SQLite)

**Test Commands:**
```bash
# Concurrent requests test
seq 1 100 | xargs -P 50 -I {} curl -X POST http://localhost:7443/v1/ask \
  -H "X-API-Key: $ROUTER_ADMIN_API_KEY" \
  -d '{"prompt":"test"}'

# Large payload test
python3 -c "import json; print(json.dumps({'prompt': 'a' * 100000}))" | \
  curl -X POST http://localhost:7443/v1/ask \
  -H "X-API-Key: $ROUTER_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d @-
```

---

## Network Security

### TLS/SSL (if applicable)
- [ ] Test TLS version (should be ≥1.2)
- [ ] Test cipher suite configuration
- [ ] Test certificate validation
- [ ] Test for man-in-the-middle vulnerabilities

### Network Segmentation
- [ ] Verify internal services not exposed
- [ ] Test firewall rules
- [ ] Verify database access restricted

---

## Security Test Report Template

After completing tests, document findings:

### Summary
- Total tests performed: ___
- Vulnerabilities found: ___
- Critical: ___
- High: ___
- Medium: ___
- Low: ___

### Critical Findings
1. [Description]
   - **Severity:** Critical
   - **Location:** [File:Line]
   - **Impact:** [Description]
   - **Remediation:** [Steps to fix]

### Recommendations
1. [Priority 1 recommendations]
2. [Priority 2 recommendations]

### Sign-off
- **Tested by:** ___________
- **Date:** ___________
- **Status:** Pass / Fail / Pass with exceptions

---

## Automated Security Testing

### CI/CD Integration

```yaml
# .github/workflows/security.yml
name: Security Tests
on: [push, pull_request]
jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run safety check
        run: |
          pip install safety
          safety check --json
      - name: Run bandit
        run: |
          pip install bandit
          bandit -r router_service/ -f json
      - name: Run OWASP dependency check
        uses: dependency-check/Dependency-Check_Action@main
```

### Tools to Use
- **OWASP ZAP** - Web application security scanner
- **Burp Suite** - Security testing toolkit
- **Safety** - Python dependency vulnerability scanner
- **Bandit** - Python security linter
- **pytest-security** - Security-focused pytest plugin

---

## Next Steps

1. Complete all checklist items
2. Document findings in security test report
3. Create tickets for identified vulnerabilities
4. Retest after fixes applied
5. Schedule regular security testing (quarterly recommended)

## References

- OWASP Top 10 2021: https://owasp.org/Top10/
- OWASP Testing Guide: https://owasp.org/www-project-web-security-testing-guide/
- ATP AUDIT_REPORT.md
- ATP SECURITY.md

---

**Last Review:** 2025-11-17
**Next Scheduled Review:** 2026-02-17
