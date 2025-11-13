#!/usr/bin/env python3
"""Tests for Adaptive Window RL Refinement (GAP-183).

Comprehensive tests validating the RL agent, training loop, and integration
with the AIMD controller.
"""

import os
import tempfile
from unittest.mock import patch

import pytest

from router_service.window_update import AIMDController
from tools.adaptive_window_rl import (
    AdaptiveWindowRLAgent,
    RLState,
    RLTrainingLoop,
)


class TestAdaptiveWindowRLAgent:
    """Test the RL agent functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.aimd = AIMDController()
        self.agent = AdaptiveWindowRLAgent(self.aimd)

    def test_initialization(self):
        """Test agent initialization with default parameters."""
        assert self.agent.learning_rate == 0.1
        assert self.agent.discount_factor == 0.9
        assert self.agent.exploration_rate == 0.1
        assert len(self.agent.action_space) == 7  # Default action space
        assert len(self.agent.q_table) == 0  # Empty initially

    def test_state_discretization(self):
        """Test state discretization into bins."""
        state = RLState(
            current_window=16, latency_ms=750, throughput=75, error_rate=0.02, time_since_last_adjustment=120
        )

        discrete_state = self.agent.discretize_state(state)

        # Check that we get a 5-tuple (window, latency, throughput, error, time)
        assert len(discrete_state) == 5
        assert all(isinstance(x, int) for x in discrete_state)

    def test_get_state(self):
        """Test getting current state for a session."""
        session = "test_session"

        # Mock AIMD controller
        with patch.object(self.aimd, "get", return_value=32):
            state = self.agent.get_state(session, 1000.0, 50.0, 0.01)

            assert state.current_window == 32
            assert state.latency_ms == 1000.0
            assert state.throughput == 50.0
            assert state.error_rate == 0.01
            assert isinstance(state.time_since_last_adjustment, float)

    def test_select_action_exploration(self):
        """Test action selection with exploration."""
        state = RLState(16, 750, 75, 0.02, 120)

        # Force exploration
        self.agent.exploration_rate = 1.0

        action_idx = self.agent.select_action(state)
        assert 0 <= action_idx < len(self.agent.action_space)

    def test_select_action_exploitation(self):
        """Test action selection with exploitation."""
        state = RLState(16, 750, 75, 0.02, 120)

        # Force exploitation
        self.agent.exploration_rate = 0.0

        # Manually set Q-values to prefer action 0
        state_tuple = self.agent.discretize_state(state)
        self.agent.q_table[state_tuple][0] = 10.0
        self.agent.q_table[state_tuple][1] = 1.0

        action_idx = self.agent.select_action(state)
        assert action_idx == 0

    def test_apply_action(self):
        """Test applying actions to AIMD controller."""
        original_add = self.aimd.add
        original_mult = self.aimd.mult

        # Test action that increases add factor
        action_idx = 1  # RLAction(add_delta=1, mult_delta=0.0)
        self.agent.apply_action(action_idx)

        assert self.aimd.add == original_add + 1
        assert self.aimd.mult == original_mult

    def test_calculate_reward(self):
        """Test reward calculation."""
        # Good state: low latency, high throughput, low error
        good_state = RLState(32, 500, 150, 0.005, 60)
        reward = self.agent.calculate_reward(good_state)

        assert reward > 0  # Should be positive

        # Bad state: high latency, low throughput, high error
        bad_state = RLState(64, 2500, 10, 0.15, 60)
        bad_reward = self.agent.calculate_reward(bad_state)

        assert bad_reward < 0  # Should be negative
        assert bad_reward < reward  # Should be worse than good state

    def test_q_table_update(self):
        """Test Q-table learning update."""
        state1 = RLState(16, 750, 75, 0.02, 120)
        state2 = RLState(20, 800, 80, 0.02, 130)
        action_idx = 0

        # Initial Q-value
        state_tuple = self.agent.discretize_state(state1)
        initial_q = self.agent.q_table[state_tuple][action_idx]

        # Update with positive reward
        self.agent.update_q_table(state1, action_idx, 1.0, state2)

        # Q-value should increase
        updated_q = self.agent.q_table[state_tuple][action_idx]
        assert updated_q > initial_q

    def test_get_optimal_parameters(self):
        """Test getting optimal parameters."""
        params = self.agent.get_optimal_parameters()

        required_keys = ["add", "mult", "learning_rate", "exploration_rate", "total_adjustments"]
        for key in required_keys:
            assert key in params
            assert isinstance(params[key], (int, float))

    def test_save_load_model(self):
        """Test saving and loading the model."""
        # Add some Q-values
        state = RLState(16, 750, 75, 0.02, 120)
        state_tuple = self.agent.discretize_state(state)
        self.agent.q_table[state_tuple][0] = 5.0

        # Save model
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_file = f.name

        try:
            self.agent.save_model(temp_file)

            # Create new agent and load model
            new_aimd = AIMDController()
            new_agent = AdaptiveWindowRLAgent(new_aimd)
            new_agent.load_model(temp_file)

            # Check that Q-table was loaded
            assert new_agent.q_table[state_tuple][0] == 5.0

        finally:
            os.unlink(temp_file)


class TestRLTrainingLoop:
    """Test the RL training loop."""

    def setup_method(self):
        """Set up test fixtures."""
        self.aimd = AIMDController()
        self.agent = AdaptiveWindowRLAgent(self.aimd)
        self.trainer = RLTrainingLoop(self.agent, episodes=5)

    @pytest.mark.asyncio
    async def test_simulate_environment(self):
        """Test environment simulation."""
        result = await self.trainer.simulate_environment(0)

        required_keys = [
            "episode",
            "final_window",
            "final_latency",
            "final_throughput",
            "final_error_rate",
            "add_parameter",
            "mult_parameter",
            "total_adjustments",
        ]

        for key in required_keys:
            assert key in result
            assert isinstance(result[key], (int, float))

    @pytest.mark.asyncio
    async def test_run_training(self):
        """Test complete training run."""
        history = await self.trainer.run_training()

        assert len(history) == 5  # 5 episodes
        assert len(self.trainer.training_history) == 5

        # Check that all episodes have required data
        for episode_data in history:
            assert "episode" in episode_data
            assert "final_window" in episode_data

    def test_get_training_summary(self):
        """Test training summary calculation."""
        # Add mock training data
        self.trainer.training_history = [
            {
                "episode": 0,
                "final_latency": 1000.0,
                "final_throughput": 50.0,
                "final_error_rate": 0.02,
                "total_adjustments": 5,
            },
            {
                "episode": 1,
                "final_latency": 1200.0,
                "final_throughput": 45.0,
                "final_error_rate": 0.03,
                "total_adjustments": 7,
            },
        ]

        summary = self.trainer.get_training_summary()

        assert "avg_final_latency" in summary
        assert "avg_final_throughput" in summary
        assert "avg_final_error_rate" in summary
        assert "total_adjustments" in summary
        assert summary["training_episodes"] == 2


class TestRLIntegration:
    """Integration tests for RL system."""

    @pytest.mark.asyncio
    async def test_full_rl_workflow(self):
        """Test complete RL workflow from training to inference."""
        # Create components
        aimd = AIMDController()
        agent = AdaptiveWindowRLAgent(aimd, exploration_rate=0.5)  # Higher exploration for testing
        trainer = RLTrainingLoop(agent, episodes=3)

        # Run training
        history = await trainer.run_training()

        # Verify training produced results
        assert len(history) == 3
        summary = trainer.get_training_summary()
        assert summary["training_episodes"] == 3

        # Test inference (learning from feedback)
        session = "test_session"
        agent.learn_from_feedback(session, 1000.0, 50.0, 0.01, success=True)

        # Check that parameters were adjusted
        params = agent.get_optimal_parameters()
        assert params["total_adjustments"] >= 1

    def test_rl_action_space(self):
        """Test that action space covers meaningful adjustments."""
        agent = AdaptiveWindowRLAgent(AIMDController())

        # Check that we have a reasonable number of actions
        assert len(agent.action_space) >= 5

        # Check that actions include both add and mult adjustments
        has_add_adjustment = any(action.add_delta != 0 for action in agent.action_space)
        has_mult_adjustment = any(action.mult_delta != 0 for action in agent.action_space)

        assert has_add_adjustment
        assert has_mult_adjustment

    def test_reward_function_properties(self):
        """Test reward function properties."""
        agent = AdaptiveWindowRLAgent(AIMDController())

        # Test that better states get higher rewards
        good_state = RLState(32, 500, 150, 0.005, 60)
        bad_state = RLState(64, 2500, 10, 0.15, 60)

        good_reward = agent.calculate_reward(good_state)
        bad_reward = agent.calculate_reward(bad_state)

        assert good_reward > bad_reward

        # Test stability reward (gradual changes preferred)
        stable_prev = RLState(30, 500, 150, 0.005, 60)
        stable_current = RLState(32, 500, 150, 0.005, 60)  # Small change
        unstable_current = RLState(50, 500, 150, 0.005, 60)  # Large change

        stable_reward = agent.calculate_reward(stable_current, stable_prev)
        unstable_reward = agent.calculate_reward(unstable_current, stable_prev)

        assert stable_reward >= unstable_reward


class TestRLMetrics:
    """Test RL metrics collection."""

    def test_metrics_initialization(self):
        """Test that RL metrics are properly initialized."""
        aimd = AIMDController()
        agent = AdaptiveWindowRLAgent(aimd)

        # Check that metrics counters exist
        assert hasattr(agent, "_metrics_rl_adjustments")
        assert hasattr(agent, "_metrics_rl_rewards")
        assert hasattr(agent, "_metrics_rl_exploration")
        assert hasattr(agent, "_metrics_rl_exploitation")

    def test_metrics_updates(self):
        """Test that metrics are updated during RL operations."""
        aimd = AIMDController()
        agent = AdaptiveWindowRLAgent(aimd)

        # Perform some actions to trigger metrics updates
        state = RLState(16, 750, 75, 0.02, 120)

        # Select action (should increment exploration or exploitation counter)
        initial_exploration = agent._metrics_rl_exploration.value
        initial_exploitation = agent._metrics_rl_exploitation.value

        agent.select_action(state)

        # One of the counters should have increased
        final_exploration = agent._metrics_rl_exploration.value
        final_exploitation = agent._metrics_rl_exploitation.value

        assert (final_exploration > initial_exploration) or (final_exploitation > initial_exploitation)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
