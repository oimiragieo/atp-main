"""Namespace / tenant enforcement & access controls POC.
Implements a simple policy engine that authorizes actions based on (tenant, namespace, action)
triples using allow rules and a default deny.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    tenant: str
    namespace: str
    action: str  # e.g. read, write, admin


class AccessPolicy:
    def __init__(self, rules: list[Rule]):
        self.rules = set(rules)

    def allowed(self, tenant: str, namespace: str, action: str) -> bool:
        # wildcard fallbacks
        return (
            Rule(tenant, namespace, action) in self.rules
            or Rule(tenant, namespace, "*") in self.rules
            or Rule(tenant, "*", action) in self.rules
            or Rule(tenant, "*", "*") in self.rules
        )


if __name__ == "__main__":
    policy = AccessPolicy(
        [
            Rule("t1", "ns1", "read"),
            Rule("t1", "ns1", "write"),
            Rule("t1", "*", "read"),
            Rule("t2", "nsX", "admin"),
        ]
    )
    assert policy.allowed("t1", "ns1", "read")
    assert policy.allowed("t1", "ns2", "read")  # wildcard namespace
    assert not policy.allowed("t1", "ns2", "write")
    assert not policy.allowed("t2", "nsX", "read")
    assert policy.allowed("t2", "nsX", "admin")
    print("OK: namespace access controls POC passed")
