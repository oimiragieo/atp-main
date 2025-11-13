"""Policy-Driven Tool Permissions POC
Evaluates tool invocation requests against policy rules with allow/deny patterns and LLM red-team simulation stub.
"""

from dataclasses import dataclass


@dataclass
class Rule:
    effect: str  # ALLOW or DENY
    pattern: str


class ToolPolicy:
    def __init__(self, rules: list[Rule]):
        self.rules = rules

    def decide(self, tool_name: str):
        decision = "DENY"
        for r in self.rules:
            if r.pattern in tool_name:
                decision = r.effect
        return decision


def simulate_red_team(prompt: str):
    # naive heuristic: block if suspicious substrings
    bad = any(x in prompt.lower() for x in ["exfiltrate", "steal", "rm -rf"])
    return not bad


if __name__ == "__main__":
    policy = ToolPolicy([Rule("ALLOW", "search"), Rule("DENY", "system")])
    ok1 = policy.decide("vector_search") == "ALLOW"
    ok2 = policy.decide("system_exec") == "DENY"
    ok3 = simulate_red_team("Please exfiltrate secrets") is False
    if ok1 and ok2 and ok3:
        print("OK: policy tool permissions POC passed")
    else:
        print("FAIL: policy tool permissions POC", ok1, ok2, ok3)
