"""Policy Engine Aggregate POC
Combines: scoring selection, champion/challenger escalation, disagreement trigger, and bandit exploration.
"""

import os
import random
import sys
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.champion_challenger_poc import Candidate as CCand
from tools.champion_challenger_poc import select as champion_select
from tools.disagreement_poc import disagreement
from tools.routing_poc import Candidate as ScoreCandidate
from tools.routing_poc import select_adapters
from tools.thompson_bandit_poc import Arm, select_arm, update


@dataclass
class PolicyDecision:
    primary: str
    secondaries: list[str]
    strategy: str
    meta: dict[str, Any]


class PolicyEngine:
    def __init__(self):
        self.bandit_arms = [Arm("cheap"), Arm("balanced"), Arm("premium")]

    def decide(
        self, adapters: list[dict[str, Any]], need_ctx: int, budget: int, disagreement_sets=None
    ) -> PolicyDecision:
        # 1. Score-based shortlist
        scored = [
            ScoreCandidate(a["name"], a["ctx"], a["est_in"], a["est_out"], a["usd"], a["p95"], a["confidence"])
            for a in adapters
        ]
        shortlist = select_adapters(scored, k=3, required_ctx=need_ctx, budget_usd_micros=budget)
        if not shortlist:
            return PolicyDecision("none", [], "none", {"reason": "no_feasible"})
        # 2. Champion/challenger
        cc_in = [CCand(a.name, a.confidence, a.usd_micros) for a in shortlist]
        champ, challenger, escalated = champion_select(cc_in, min_conf=0.7)
        secondaries = []
        if escalated and challenger:
            secondaries.append(challenger.name)
        # 3. Disagreement trigger to add diversity if high disagreement
        if disagreement_sets and disagreement(disagreement_sets) > 0.4:
            others = [c.name for c in shortlist if c.name not in {champ.name, *secondaries}]
            if others:
                secondaries.append(random.choice(others))
        # 4. Bandit exploration: occasionally swap primary with bandit-chosen archetype
        arm_index = select_arm(self.bandit_arms)
        chosen_arm = self.bandit_arms[arm_index].name
        archetype_map = {"cheap": "cheap", "balanced": "mid", "premium": "expensive"}
        if random.random() < 0.15:  # 15% exploration
            for c in shortlist:
                if archetype_map[chosen_arm] in c.name:
                    secondaries.insert(0, champ.name)
                    champ = CCand(c.name, c.confidence, c.usd_micros)
                    break
        decision = PolicyDecision(
            champ.name, secondaries, "aggregate", {"escalated": escalated, "explore_arm": chosen_arm}
        )
        # Dummy bandit reward: success if champion usd under half budget
        reward = 1 if champ.usd_micros < budget / 2 else 0
        update(self.bandit_arms[arm_index], reward)
        return decision


if __name__ == "__main__":
    engine = PolicyEngine()
    adapters = [
        {
            "name": "cheap-fast",
            "ctx": 32000,
            "est_in": 2000,
            "est_out": 500,
            "usd": 10000,
            "p95": 300,
            "confidence": 0.62,
        },
        {"name": "mid", "ctx": 128000, "est_in": 2000, "est_out": 500, "usd": 80000, "p95": 600, "confidence": 0.75},
        {
            "name": "expensive-strong",
            "ctx": 1000000,
            "est_in": 2000,
            "est_out": 500,
            "usd": 300000,
            "p95": 900,
            "confidence": 0.88,
        },
    ]
    sets = [{"a", "b", "c"}, {"a", "c", "d"}, {"x", "y"}]
    dec = engine.decide(adapters, need_ctx=8000, budget=120000, disagreement_sets=[set(s) for s in sets])
    assert dec.primary in {"cheap-fast", "mid", "expensive-strong"}
    assert dec.strategy == "aggregate"
    print("OK: policy engine POC passed")
