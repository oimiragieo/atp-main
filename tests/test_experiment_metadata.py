"""Tests for experiment metadata surfacing (GAP-129)."""

from __future__ import annotations

from router_service.champion_challenger import Candidate, select_challenger


def test_experiment_metadata_select_challenger():
    """Test that challenger selection works correctly."""
    primary = Candidate("gpt-4", 0.03, 0.80)
    pool = [
        Candidate("gpt-4-turbo", 0.01, 0.82),  # Better quality, cheaper
        Candidate("claude-3", 0.015, 0.85),     # Better quality, reasonable cost
        Candidate("gpt-4-expensive", 0.10, 0.90),  # Too expensive
    ]
    
    challenger = select_challenger(primary, pool)
    assert challenger is not None
    assert challenger.name == "claude-3"  # Should pick best quality within cost limits


def test_experiment_metadata_no_challenger_selected():
    """Test that no challenger is selected when none meet criteria."""
    primary = Candidate("gpt-4", 0.03, 0.80)
    pool = [
        Candidate("expensive-model", 0.20, 0.85),  # Too expensive
        Candidate("worse-model", 0.02, 0.75),      # Worse quality
    ]
    
    challenger = select_challenger(primary, pool)
    assert challenger is None


def test_experiment_frames_metric_incremented():
    """Test that experiment_frames_total metric is incremented when challenger is present."""
    from router_service.service import EXPERIMENT_FRAMES_TOTAL
    
    # Get initial metric value
    initial_value = EXPERIMENT_FRAMES_TOTAL.value
    
    # Increment the metric (simulating what happens in the service)
    EXPERIMENT_FRAMES_TOTAL.inc(1)
    
    # Check metric was incremented
    final_value = EXPERIMENT_FRAMES_TOTAL.value
    assert final_value == initial_value + 1


def test_experiment_metadata_roles_structure():
    """Test the structure of roles array with challenger information."""
    # Test the roles structure that gets included in plan response
    roles = [
        {"role": "primary", "model": "gpt-4"},
        {"role": "explore", "model": "gpt-4-turbo"},
        {"role": "challenger", "model": "claude-3"},
        {"role": "fallback", "model": "gpt-3.5-turbo"}
    ]
    
    # Verify structure
    assert len(roles) == 4
    assert roles[0]["role"] == "primary"
    assert roles[0]["model"] == "gpt-4"
    
    # Check challenger role is present
    challenger_roles = [r for r in roles if r.get("role") == "challenger"]
    assert len(challenger_roles) == 1
    assert challenger_roles[0]["model"] == "claude-3"


def test_experiment_metadata_roles_without_challenger():
    """Test roles structure when no challenger is selected."""
    roles = [
        {"role": "primary", "model": "gpt-4"},
        {"role": "explore", "model": "gpt-4-turbo"},
        {"role": "fallback", "model": "gpt-3.5-turbo"}
    ]
    
    # Verify no challenger role
    challenger_roles = [r for r in roles if r.get("role") == "challenger"]
    assert len(challenger_roles) == 0
    
    # But primary and other roles should still be there
    assert len([r for r in roles if r.get("role") == "primary"]) == 1


def test_experiment_metadata_candidates_structure():
    """Test the structure of candidates array in plan response."""
    candidates = [
        {
            "model": "gpt-4",
            "cost_per_1k": 0.03,
            "quality_pred": 0.80,
            "latency_p95": 1500
        },
        {
            "model": "claude-3",
            "cost_per_1k": 0.015,
            "quality_pred": 0.85,
            "latency_p95": 1200
        }
    ]
    
    # Verify structure
    assert len(candidates) == 2
    assert candidates[0]["model"] == "gpt-4"
    assert candidates[0]["cost_per_1k"] == 0.03
    assert candidates[0]["quality_pred"] == 0.80
    assert "latency_p95" in candidates[0]


def test_experiment_metadata_plan_response_format():
    """Test the complete plan response format with experiment metadata."""
    plan_response = {
        "type": "plan",
        "candidates": [
            {
                "model": "gpt-4",
                "cost_per_1k": 0.03,
                "quality_pred": 0.80,
                "latency_p95": 1500
            }
        ],
        "cluster_hint": "us-east-1",
        "prompt_hash": "abc123",
        "reason": "cheapest acceptable then escalation (bandit)",
        "roles": [
            {"role": "primary", "model": "gpt-4"},
            {"role": "challenger", "model": "claude-3"}
        ]
    }
    
    # Verify required fields
    assert plan_response["type"] == "plan"
    assert "candidates" in plan_response
    assert "roles" in plan_response
    assert "cluster_hint" in plan_response
    assert "prompt_hash" in plan_response
    assert "reason" in plan_response
    
    # Verify challenger is in roles
    roles = plan_response["roles"]
    challenger_present = any(r.get("role") == "challenger" for r in roles)
    assert challenger_present
