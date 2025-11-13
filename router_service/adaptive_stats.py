"""Adaptive routing statistics persistence & UCB / Thompson helpers."""

import math
import os
import random
import sqlite3
import threading
from collections.abc import Sequence
from typing import Optional, Protocol

# Try to import contextual features, fallback to None if not available
try:
    from .contextual_ucb import CONTEXTUAL_FEATURE_EXTRACTOR, CONTEXTUAL_UCB
except ImportError:
    CONTEXTUAL_FEATURE_EXTRACTOR = None
    CONTEXTUAL_UCB = None


class HasName(Protocol):
    name: str


DB_PATH = os.path.join(os.path.dirname(__file__), "router_stats.sqlite")
_LOCK = threading.Lock()


def init_db() -> None:
    with _LOCK:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS model_stats (
                cluster TEXT,
                model TEXT,
                calls INTEGER,
                success INTEGER,
                cost_sum REAL,
                latency_sum REAL,
                PRIMARY KEY(cluster, model)
            )"""
        )
        conn.commit()
        conn.close()


def update_stat(
    cluster: str,
    model: str,
    success: bool,
    cost: float,
    latency: float,
    prompt: Optional[str] = None,
    latency_slo_ms: Optional[float] = None,
) -> None:
    with _LOCK:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT calls, success, cost_sum, latency_sum FROM model_stats WHERE cluster=? AND model=?",
            (cluster, model),
        )
        row = c.fetchone()
        if row:
            calls, succ, cost_sum, lat_sum = row
            calls += 1
            succ += 1 if success else 0
            cost_sum += cost
            lat_sum += latency
            c.execute(
                "UPDATE model_stats SET calls=?, success=?, cost_sum=?, latency_sum=? WHERE cluster=? AND model=?",
                (calls, succ, cost_sum, lat_sum, cluster, model),
            )
        else:
            c.execute(
                "INSERT INTO model_stats (cluster, model, calls, success, cost_sum, latency_sum) VALUES (?,?,?,?,?,?)",
                (cluster, model, 1, 1 if success else 0, cost, latency),
            )
        conn.commit()
        conn.close()

        # Update contextual UCB if features provided
        if prompt is not None and CONTEXTUAL_FEATURE_EXTRACTOR is not None and CONTEXTUAL_UCB is not None:
            reward = 1.0 if success else 0.0
            # Adjust reward based on cost efficiency (higher reward for lower cost)
            if cost > 0:
                reward *= 1.0 / cost  # Reward inversely proportional to cost
            features = CONTEXTUAL_FEATURE_EXTRACTOR.get_feature_vector(prompt, latency_slo_ms)
            CONTEXTUAL_UCB.update(model, features, reward)


def fetch_stats(cluster: str) -> list[tuple[str, int, int, float, float]]:
    with _LOCK:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT model, calls, success, cost_sum, latency_sum FROM model_stats WHERE cluster=?", (cluster,))
        data = c.fetchall()
        conn.close()
    # rows: model, calls, success, cost_sum, latency_sum
    return [
        (str(m), int(calls), int(succ), float(cost_sum), float(lat_sum)) for (m, calls, succ, cost_sum, lat_sum) in data
    ]


def fetch_all_clusters() -> list[str]:
    with _LOCK:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT DISTINCT cluster FROM model_stats")
        rows = c.fetchall()
        conn.close()
    return [r[0] for r in rows]


def ucb_select(
    cluster: str,
    candidates: Sequence[HasName],
    explore_factor: float = 1.4,
    prompt: Optional[str] = None,
    latency_slo_ms: Optional[float] = None,
) -> Optional[str]:
    """Return model name chosen by UCB on success rate / cost ratio.
    Score = (success/calls) / avg_cost + explore_factor * sqrt(log(total_calls)/calls).
    If contextual features provided, uses contextual UCB scoring.
    Fallback to first candidate if insufficient data.
    """
    stats = fetch_stats(cluster)
    if not stats:
        return None

    stat_map = {m: (calls, success, cost_sum) for m, calls, success, cost_sum, _lat_sum in stats}
    total_calls = sum(v[0] for v in stat_map.values())

    # Use contextual UCB if features provided
    if prompt is not None and CONTEXTUAL_FEATURE_EXTRACTOR is not None and CONTEXTUAL_UCB is not None:
        features = CONTEXTUAL_FEATURE_EXTRACTOR.get_feature_vector(prompt, latency_slo_ms)
        best_model: Optional[str] = None
        best_score: float = -1.0

        for c in candidates:
            m = c.name
            calls, success, cost_sum = stat_map.get(m, (0, 0, 0.0))
            if calls == 0:
                # Prioritize unseen models for exploration
                return m

            # Base score from historical data
            success_rate = success / calls if calls else 0.0
            avg_cost = (cost_sum / calls) if calls and cost_sum > 0 else 0.000001
            base_score = success_rate / avg_cost

            # Contextual score
            contextual_score = CONTEXTUAL_UCB.predict(m, features)

            # Combine base and contextual scores
            score = (
                0.7 * base_score
                + 0.3 * contextual_score
                + explore_factor * math.sqrt(math.log(total_calls + 1) / calls)
            )

            if score > best_score:
                best_score = score
                best_model = m
        return best_model

    # Fallback to original UCB without contextual features
    best_model: Optional[str] = None
    best_score: float = -1.0
    for c in candidates:
        m = c.name
        calls, success, cost_sum = stat_map.get(m, (0, 0, 0.0))
        if calls == 0:
            # prioritize unseen
            return m
        success_rate = success / calls if calls else 0.0
        avg_cost = (cost_sum / calls) if calls and cost_sum > 0 else 0.000001
        exploit = success_rate / avg_cost
        explore = math.sqrt(math.log(total_calls + 1) / calls)
        score = exploit + explore_factor * explore
        if score > best_score:
            best_score = score
            best_model = m
    return best_model


def compute_ucb_scores(
    cluster: str, explore_factor: float = 1.4, prompt: Optional[str] = None, latency_slo_ms: Optional[float] = None
) -> dict[str, dict[str, float]]:
    """Return mapping model -> {score, exploit, explore} for cluster.
    If contextual features provided, includes contextual scoring.
    """
    stats = fetch_stats(cluster)
    if not stats:
        return {}
    stat_map = {m: (calls, success, cost_sum) for m, calls, success, cost_sum, _lat_sum in stats}
    total_calls = sum(v[0] for v in stat_map.values())

    # Use contextual features if provided
    features = None
    if prompt is not None and CONTEXTUAL_FEATURE_EXTRACTOR is not None:
        features = CONTEXTUAL_FEATURE_EXTRACTOR.get_feature_vector(prompt, latency_slo_ms)

    out = {}
    for m, (calls, success, cost_sum) in stat_map.items():
        if calls == 0:
            out[m] = {"score": 0.0, "exploit": 0.0, "explore": 0.0, "contextual": 0.0}
            continue
        success_rate = success / calls if calls else 0.0
        avg_cost = (cost_sum / calls) if calls and cost_sum > 0 else 0.000001
        exploit = success_rate / avg_cost
        explore = math.sqrt(math.log(total_calls + 1) / calls) * explore_factor

        contextual_score = 0.0
        if features is not None and CONTEXTUAL_UCB is not None:
            contextual_score = CONTEXTUAL_UCB.predict(m, features)

        # Combined score
        score = exploit + explore
        if features is not None:
            score = 0.7 * (exploit + explore) + 0.3 * contextual_score

        out[m] = {"score": score, "exploit": exploit, "explore": explore, "contextual": contextual_score}
    return out


def thompson_select(cluster: str, candidates: Sequence[HasName]) -> Optional[str]:
    """Simple Thompson Sampling on success probability ignoring cost for now.
    Draw Beta(success+1, fails+1); choose max; if unseen prefer exploration.
    """
    stats = fetch_stats(cluster)
    stat_map = {m: (calls, success) for m, calls, success, _cost_sum, _lat_sum in stats}
    # Any unseen -> random unseen to encourage data gathering
    unseen: list[str] = [c.name for c in candidates if c.name not in stat_map]
    if unseen:
        return random.choice(unseen)
    best: Optional[str] = None
    best_draw: float = -1.0
    import random as _r

    for c in candidates:
        name = c.name
        calls, success = stat_map.get(name, (0, 0))
        fails = max(calls - success, 0)
        # Beta draw
        draw = _r.betavariate(success + 1, fails + 1)
        if draw > best_draw:
            best_draw = draw
            best = name
    return best
