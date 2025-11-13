"""Admin console POC.
Provides in-memory registry for rollout stages and integrates existing policy simulator to dry-run routing decisions.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dataclasses import dataclass
from typing import Any

from tools.policy_sim_poc import simulate


@dataclass
class Rollout:
    name: str
    stable: str
    canary: str
    percent: int  # percent traffic to canary


class AdminConsole:
    def __init__(self):
        self.rollouts: dict[str, Rollout] = {}

    def create_rollout(self, name: str, stable: str, canary: str, percent: int):
        if name in self.rollouts:
            raise ValueError("exists")
        self.rollouts[name] = Rollout(name, stable, canary, percent)

    def update_percent(self, name: str, percent: int):
        self.rollouts[name].percent = percent

    def dry_run_policy(self, policy_path: str, ctx: dict[str, Any]):
        return simulate(policy_path, ctx)


if __name__ == "__main__":
    console = AdminConsole()
    console.create_rollout("adapter-v2", "adapter-v1", "adapter-v2", 10)
    policy_path = os.path.join(os.path.dirname(__file__), "policy_poc.yaml")
    decision = console.dry_run_policy(policy_path, {"tenant": "acme", "adapter": "adapter-v2", "data_scope": []})
    assert decision["decision"] in {"allow", "deny"}
    console.update_percent("adapter-v2", 50)
    assert console.rollouts["adapter-v2"].percent == 50
    print("OK: admin console POC passed; decision=", decision)
