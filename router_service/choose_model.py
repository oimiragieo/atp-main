"""Cheapest acceptable routing heuristic with carbon intensity influence.
Not production: uses static priors; future wiring: dynamic stats.
"""

import os
import random
from typing import Any, Optional

from metrics.registry import CARBON_AWARE_ROUTING_DECISIONS_TOTAL, CARBON_INTENSITY_WEIGHT

from .carbon_energy_attribution import CarbonEnergyAttribution
from .carbon_intensity_tracker import get_carbon_tracker
from .regret_calculator import RegretAnalysis, get_regret_calculator
from .routing_constants import CATALOG, QUALITY_THRESH, Candidate


def choose(
    quality: str,
    latency_slo_ms: int,
    registry: dict[str, Any],
    required_safety: str = "A",
    carbon_aware: bool = True,
    total_tokens: int = 1000,
) -> tuple[list[Candidate], Optional[RegretAnalysis], dict[str, Any]]:
    q_min = QUALITY_THRESH.get(quality, 0.75)
    ordered = sorted(CATALOG, key=lambda c: c.cost_per_1k_tokens)

    # Apply carbon intensity influence if enabled
    if carbon_aware:
        CARBON_AWARE_ROUTING_DECISIONS_TOTAL.inc()
        carbon_tracker = get_carbon_tracker()
        # Sort by carbon-adjusted cost (cost * carbon penalty)
        ordered = sorted(ordered, key=lambda c: carbon_tracker.calculate_routing_weight(c.region, c.cost_per_1k_tokens))

        # Update carbon intensity weight metric for the selected region
        if ordered:
            primary_candidate = ordered[0]
            weight = carbon_tracker.calculate_routing_weight(
                primary_candidate.region, primary_candidate.cost_per_1k_tokens
            )
            CARBON_INTENSITY_WEIGHT.set(weight)

    plan: list[Candidate] = []
    # Optional exploration: with small probability, sample a non-primary candidate meeting latency to gather data
    explore_p = float(os.getenv("ROUTER_EXPLORE_P", "0.05"))
    for c in ordered:
        rec = registry.get(c.name, {})
        # Skip shadow models from primary plan until promoted
        if rec.get("status") == "shadow":
            continue
        # basic safety gate
        grade = rec.get("safety_grade", "A")
        if grade < required_safety:
            continue
        if c.quality_pred >= q_min and c.latency_p95 <= latency_slo_ms:
            plan.append(c)
            break
    if not plan:
        # fallback highest quality under latency or cheapest overall
        viable = [c for c in ordered if c.latency_p95 <= latency_slo_ms] or ordered
        plan.append(max(viable, key=lambda c: c.quality_pred))

    # Calculate regret for the primary choice
    regret_analysis = None
    energy_attribution = {}
    if plan:
        regret_calculator = get_regret_calculator()
        regret_analysis = regret_calculator.calculate_regret(
            chosen=plan[0],
            all_candidates=CATALOG,
            quality=quality,
            latency_slo_ms=latency_slo_ms,
            registry=registry,
            total_tokens=total_tokens,
        )

        # Calculate energy attribution for the chosen model
        energy_calculator = CarbonEnergyAttribution()
        chosen_model = plan[0]

        # Determine model category based on cost (rough heuristic)
        if chosen_model.cost_per_1k_tokens < 0.5:
            model_category = "specialist_slm"
        elif chosen_model.cost_per_1k_tokens < 1.5:
            model_category = "general_slm"
        else:
            model_category = "large_model"

        energy_kwh = energy_calculator.calculate_energy_consumption(chosen_model.name, total_tokens, model_category)
        co2e_grams = energy_calculator.calculate_co2e_emissions(energy_kwh, chosen_model.region)

        energy_attribution = {
            "model_name": chosen_model.name,
            "model_category": model_category,
            "energy_kwh": energy_kwh,
            "co2e_grams": co2e_grams,
            "region": chosen_model.region,
            "total_tokens": total_tokens,
        }

    # exploration candidate (if not already selected and passes latency)
    latency_viable = [
        c for c in ordered if c.latency_p95 <= latency_slo_ms and registry.get(c.name, {}).get("status") != "shadow"
    ]
    if random.random() < explore_p and latency_viable:
        explore_choices = [c for c in latency_viable if c.name != plan[0].name]
        if explore_choices:
            plan.append(random.choice(explore_choices))
    # ensure premium escalation as last resort if not already present
    if ordered[-1].name not in [c.name for c in plan]:
        plan.append(ordered[-1])
    return plan, regret_analysis, energy_attribution
