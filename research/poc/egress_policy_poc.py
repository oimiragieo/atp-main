import fnmatch
from urllib.parse import urlparse


def allowed(url: str, policy: dict[str, list[str]]) -> bool:
    """Return True if URL is allowed by domain patterns and optional scheme/port lists.

    policy example: {"domains":["api.example.com","*.trusted.com"], "schemes":["http","https"], "ports":[80,443]}
    """
    p = urlparse(url)
    host = p.hostname or ""
    dom_pats = policy.get("domains", ["*"])
    if not any(fnmatch.fnmatch(host, pat) for pat in dom_pats):
        return False
    schemes = policy.get("schemes")
    if schemes and p.scheme not in schemes:
        return False
    ports = policy.get("ports")
    port = p.port or (443 if p.scheme == "https" else 80)
    if ports and port not in ports:
        return False
    return True
