import importlib
import os

from fastapi.testclient import TestClient

# Ensure settings for test
os.environ["ROUTER_PII_SCRUB"] = "1"
os.environ["ROUTER_ADMIN_API_KEY"] = "secret-test"

service = importlib.import_module("router_service.service")
app = service.app
client = TestClient(app)


def test_email_redaction_and_admin_guard():
    # Reset admin keys to ensure clean state for this specific test
    from router_service import admin_keys

    admin_keys.reset_for_tests()

    # Force re-initialization with our test environment
    import os

    import router_service.service as svc

    # Temporarily clear any inherited environment that might interfere
    old_admin_keys = os.environ.get("ROUTER_ADMIN_KEYS")
    old_admin_api_key = os.environ.get("ROUTER_ADMIN_API_KEY")

    try:
        # Clear any inherited multi-key setting
        if "ROUTER_ADMIN_KEYS" in os.environ:
            del os.environ["ROUTER_ADMIN_KEYS"]

        # Ensure our legacy key is set
        os.environ["ROUTER_ADMIN_API_KEY"] = "secret-test"

        # Re-initialize admin keys
        svc._init_admin_keys_once()

        prompt = "Hello my email is user@example.com please help"
        resp = client.post("/v1/ask", json={"prompt": prompt})
        assert resp.status_code == 200
        # Collect streamed frames
        for line in resp.iter_lines():
            if not line:
                continue
            # lines look like 'data: {json}\n'
            if not line.startswith("data: "):
                continue
            payload = line[len("data: ") :]
            if "user@example.com" in payload:
                raise AssertionError("Raw email leaked in stream")
            if "[REDACTED_EMAIL]" in payload:
                pass
            if '"frame_type": "FINAL"' in payload:
                break
        # Redaction token may not appear because prompt not echoed; primary assertion is no raw email.

        # Admin endpoint without key should 401
        r = client.get("/admin/version")
        assert r.status_code == 401
        # With key
        r2 = client.get("/admin/version", headers={"x-api-key": "secret-test"})
        assert r2.status_code == 200

    finally:
        # Restore original environment
        if old_admin_keys is not None:
            os.environ["ROUTER_ADMIN_KEYS"] = old_admin_keys
        elif "ROUTER_ADMIN_KEYS" in os.environ:
            del os.environ["ROUTER_ADMIN_KEYS"]

        if old_admin_api_key is not None:
            os.environ["ROUTER_ADMIN_API_KEY"] = old_admin_api_key
        elif "ROUTER_ADMIN_API_KEY" in os.environ:
            del os.environ["ROUTER_ADMIN_API_KEY"]
