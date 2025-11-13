"""Model lifecycle (promotion/demotion) helpers extracted from service."""

import time
from typing import Any, Callable, TypedDict

from .config import settings
from .logging_utils import log_event
from .shadow_evaluation import shadow_tracker

PROMOTE_MIN_CALLS = settings.promote_min_calls
PROMOTE_COST_IMPROVE = settings.promote_cost_improve
DEMOTE_MIN_CALLS = settings.demote_min_calls
DEMOTE_COST_REGRESS = settings.demote_cost_regress
HYSTERESIS_SECONDS = settings.hysteresis_seconds

# State shared with service (will be passed in)

LifecycleAppend = Callable[[dict[str, Any]], None]
PersistFn = Callable[[dict[str, Any]], None]
RecordObsFn = Callable[[dict[str, Any]], None]


def build_promotion_reason(
    shadow_model: str,
    shadow_stats: tuple[int, int, float, float],
    primary_model: str,
    primary_stats: tuple[int, int, float, float],
    cost_threshold: float = PROMOTE_COST_IMPROVE,
) -> str:
    """GAP-217: Build a detailed reason for model promotion based on multiple criteria.

    Args:
        shadow_model: Name of the shadow model being evaluated
        shadow_stats: (calls, success, cost_sum, latency_sum) for shadow model
        primary_model: Name of the primary model being compared against
        primary_stats: (calls, success, cost_sum, latency_sum) for primary model
        cost_threshold: Cost improvement threshold (default from settings)

    Returns:
        Detailed reason string explaining why the model should be promoted
    """
    shadow_calls, shadow_success, shadow_cost_sum, shadow_latency_sum = shadow_stats
    primary_calls, primary_success, primary_cost_sum, primary_latency_sum = primary_stats

    if shadow_calls == 0 or primary_calls == 0:
        return "insufficient_data"

    # Calculate averages
    shadow_avg_cost = shadow_cost_sum / shadow_calls
    primary_avg_cost = primary_cost_sum / primary_calls
    shadow_success_rate = shadow_success / shadow_calls
    primary_success_rate = primary_success / primary_calls
    shadow_avg_latency = shadow_latency_sum / shadow_calls
    primary_avg_latency = primary_latency_sum / primary_calls

    reasons = []

    # Cost improvement
    if shadow_avg_cost < primary_avg_cost * cost_threshold:
        cost_improvement_pct = ((primary_avg_cost - shadow_avg_cost) / primary_avg_cost) * 100
        reasons.append(f"cost_improvement_{cost_improvement_pct:.1f}pct")

    # Success rate comparison
    if shadow_success_rate > primary_success_rate:
        success_diff_pct = ((shadow_success_rate - primary_success_rate) / primary_success_rate) * 100
        reasons.append(f"success_rate_improvement_{success_diff_pct:.1f}pct")

    # Latency comparison
    if shadow_avg_latency < primary_avg_latency:
        latency_improvement_pct = ((primary_avg_latency - shadow_avg_latency) / primary_avg_latency) * 100
        reasons.append(f"latency_improvement_{latency_improvement_pct:.1f}pct")

    # Determine primary reason (most significant improvement)
    if not reasons:
        return "threshold_not_met"

    # Return the most significant reason, or combine if multiple
    if len(reasons) == 1:
        return reasons[0]
    else:
        # Sort by improvement magnitude (extract numeric values)
        def get_improvement_value(reason: str) -> float:
            try:
                return float(reason.split("_")[-1].replace("pct", ""))
            except (ValueError, IndexError):
                return 0.0

        sorted_reasons = sorted(reasons, key=get_improvement_value, reverse=True)
        primary_reason = sorted_reasons[0]
        return f"{primary_reason}_plus_{len(reasons) - 1}_other_criteria"


class ModelAction(TypedDict, total=False):
    action: str
    ts: float


def initialize_promotion_tracking(model_registry: dict[str, dict[str, Any]]) -> None:
    """Initialize promotion cycle tracking for existing shadow models."""
    for model_name, rec in model_registry.items():
        if rec.get("status") == "shadow":
            shadow_tracker.record_model_candidate(model_name)
            # GAP-344: Initialize shadow evaluation tracking
            shadow_tracker.start_shadow_evaluation(model_name)


def evaluate_promotions(
    cluster_key: str,
    model_registry: dict[str, dict[str, Any]],
    model_last_action: dict[str, ModelAction],
    stats_map: dict[str, tuple[int, float]],
    lifecycle_append: LifecycleAppend,
    persist: PersistFn,
    record_obs: RecordObsFn,
    promotion_counter_ref: dict[str, int],
) -> None:
    """Check shadow models for promotion based on avg cost improvement."""
    now = time.time()
    # Identify primary reference: cheapest active cost for baseline comparison
    active_costs = [
        (m, c_sum / calls)
        for m, (calls, c_sum) in ((m, (stats_map[m][0], stats_map[m][1])) for m in stats_map)
        if m in model_registry and model_registry[m].get("status") == "active" and stats_map[m][0] > 0
    ]
    if not active_costs:
        return
    active_costs.sort(key=lambda x: x[1])
    cheapest_model, cheapest_cost = active_costs[0]
    for m, rec in model_registry.items():
        if rec.get("status") == "shadow" and m in stats_map:
            calls, cost_sum = stats_map[m]
            if calls >= PROMOTE_MIN_CALLS and cheapest_cost > 0:
                avg_shadow = cost_sum / calls

                # GAP-344: Use shadow evaluation tracker for promotion decisions
                should_promote, reason = shadow_tracker.should_promote_shadow_model(m)

                if should_promote or (not should_promote and avg_shadow < cheapest_cost * PROMOTE_COST_IMPROVE):
                    # Use shadow tracker result if available, otherwise fall back to cost-based logic
                    promotion_reason = (
                        reason if should_promote else f"Cost improvement: ${cheapest_cost:.3f} -> ${avg_shadow:.3f}"
                    )

                    last = model_last_action.get(m)
                    if last and now - last.get("ts", 0) < HYSTERESIS_SECONDS:
                        continue
                    rec["status"] = "active"
                    record_obs({"ts": time.time(), "event": "promotion", "model": m, "cluster": cluster_key})
                    log_event("model.promoted", model=m, cluster=cluster_key, reason=promotion_reason)
                    promotion_counter_ref["value"] += 1
                    model_last_action[m] = {"action": "promotion", "ts": now}

                    # GAP-344: Record promotion in shadow tracker
                    shadow_tracker.promote_model(m)

                    # GAP-217: Build detailed promotion reason
                    reason = build_promotion_reason(
                        shadow_model=m,
                        shadow_stats=(
                            calls,
                            0,
                            cost_sum,
                            0,
                        ),  # Note: success and latency not available in current stats_map
                        primary_model=cheapest_model,
                        primary_stats=(stats_map[cheapest_model][0], 0, stats_map[cheapest_model][1], 0),
                    )
                    evt = {
                        "ts": time.time(),
                        "event": "promotion",
                        "model": m,
                        "cluster": cluster_key,
                        "reason": reason,
                    }
                    lifecycle_append(evt)
                    persist(evt)
                    # GAP-201: Record promotion for cycle tracking
                    shadow_tracker.record_promotion(m)


def evaluate_demotions(
    cluster_key: str,
    model_registry: dict[str, dict[str, Any]],
    model_last_action: dict[str, ModelAction],
    stats_map: dict[str, tuple[int, float]],
    lifecycle_append: LifecycleAppend,
    persist: PersistFn,
    record_obs: RecordObsFn,
    demotion_counter_ref: dict[str, int],
) -> None:
    now = time.time()
    # Compute cost averages for active models
    active_avgs = []
    for m, rec in model_registry.items():
        if rec.get("status") == "active" and m in stats_map and stats_map[m][0] > 0:
            calls, cost_sum = stats_map[m]
            active_avgs.append((m, cost_sum / calls))
    if not active_avgs:
        return
    active_avgs.sort(key=lambda x: x[1])
    cheapest_model, cheapest_cost = active_avgs[0]
    for m, avg_cost in active_avgs[1:]:
        last = model_last_action.get(m)
        if last and now - last.get("ts", 0) < HYSTERESIS_SECONDS:
            continue
        if avg_cost > cheapest_cost * DEMOTE_COST_REGRESS:
            rec_entry = model_registry.get(m)
            if rec_entry is not None:
                rec_entry["status"] = "shadow"
                record_obs({"ts": time.time(), "event": "demotion", "model": m, "cluster": cluster_key})
                log_event("model.demoted", model=m, cluster=cluster_key, baseline=cheapest_model)
                demotion_counter_ref["value"] += 1
                model_last_action[m] = ModelAction(action="demotion", ts=time.time())
                evt = {"ts": time.time(), "event": "demotion", "model": m, "cluster": cluster_key}
                lifecycle_append(evt)
                persist(evt)
