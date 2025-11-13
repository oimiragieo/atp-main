#!/usr/bin/env python3
"""Adaptive Window RL Refinement (GAP-183).

Reinforcement Learning system to optimize AIMD window parameters adaptively.
Learns optimal additive/multiplicative factors based on latency and throughput rewards.
"""

import asyncio
import json
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from metrics.registry import REGISTRY
from router_service.window_update import AIMDController


@dataclass
class RLState:
    """State representation for RL agent."""
    current_window: int
    latency_ms: float
    throughput: float
    error_rate: float
    time_since_last_adjustment: float


@dataclass
class RLAction:
    """Action representation for RL agent."""
    add_delta: int  # Change to additive factor
    mult_delta: float  # Change to multiplicative factor


class AdaptiveWindowRLAgent:
    """Reinforcement Learning agent for adaptive window optimization."""

    def __init__(
        self,
        aimd_controller: AIMDController,
        learning_rate: float = 0.1,
        discount_factor: float = 0.9,
        exploration_rate: float = 0.1,
        state_bins: dict[str, list[float]] = None,
        action_space: list[RLAction] = None,
    ):
        self.aimd = aimd_controller
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.exploration_rate = exploration_rate

        # State discretization bins
        self.state_bins = state_bins or {
            'window': [0, 4, 8, 16, 32, 64, 128],  # Window size bins
            'latency': [0, 500, 1000, 1500, 2000, 3000],  # Latency bins (ms)
            'throughput': [0, 10, 50, 100, 200, 500],  # Throughput bins (req/s)
            'error_rate': [0, 0.01, 0.05, 0.1, 0.2, 0.5],  # Error rate bins
            'time_since_adjustment': [0, 60, 300, 900, 1800],  # Time bins (seconds)
        }

        # Action space: combinations of add/mult adjustments
        self.action_space = action_space or [
            RLAction(add_delta=0, mult_delta=0.0),    # No change
            RLAction(add_delta=1, mult_delta=0.0),    # Increase add
            RLAction(add_delta=-1, mult_delta=0.0),   # Decrease add
            RLAction(add_delta=0, mult_delta=0.1),    # Increase mult
            RLAction(add_delta=0, mult_delta=-0.1),   # Decrease mult
            RLAction(add_delta=1, mult_delta=0.05),   # Balanced increase
            RLAction(add_delta=-1, mult_delta=-0.05), # Balanced decrease
        ]

        # Q-table: state -> action -> q_value
        self.q_table: dict[tuple, dict[int, float]] = defaultdict(lambda: defaultdict(float))

        # Metrics
        self._metrics_rl_adjustments = REGISTRY.counter("rl_adjustments_total")
        self._metrics_rl_rewards = REGISTRY.histogram("rl_reward_distribution", [-10, -5, -1, 0, 1, 5, 10])
        self._metrics_rl_exploration = REGISTRY.counter("rl_exploration_actions_total")
        self._metrics_rl_exploitation = REGISTRY.counter("rl_exploitation_actions_total")

        # Training state
        self.last_state: Optional[RLState] = None
        self.last_action_idx: Optional[int] = None
        self.last_reward: Optional[float] = None
        self.episode_count = 0
        self.adjustment_count = 0

    def discretize_state(self, state: RLState) -> tuple:
        """Convert continuous state to discrete tuple for Q-table."""
        def find_bin(value: float, bins: list[float]) -> int:
            for i, bin_edge in enumerate(bins[1:], 1):
                if value <= bin_edge:
                    return i - 1
            return len(bins) - 2  # Last bin

        window_bin = find_bin(state.current_window, self.state_bins['window'])
        latency_bin = find_bin(state.latency_ms, self.state_bins['latency'])
        throughput_bin = find_bin(state.throughput, self.state_bins['throughput'])
        error_bin = find_bin(state.error_rate, self.state_bins['error_rate'])
        time_bin = find_bin(state.time_since_last_adjustment, self.state_bins['time_since_adjustment'])

        return (window_bin, latency_bin, throughput_bin, error_bin, time_bin)

    def get_state(self, session: str, latency_ms: float, throughput: float,
                  error_rate: float) -> RLState:
        """Get current state for a session."""
        current_window = self.aimd.get(session)
        time_since_adjustment = time.time() - getattr(self, '_last_adjustment_time', time.time())

        return RLState(
            current_window=current_window,
            latency_ms=latency_ms,
            throughput=throughput,
            error_rate=error_rate,
            time_since_last_adjustment=time_since_adjustment
        )

    def select_action(self, state: RLState) -> int:
        """Select action using epsilon-greedy policy."""
        state_tuple = self.discretize_state(state)

        if random.random() < self.exploration_rate:
            # Exploration: random action
            action_idx = random.randint(0, len(self.action_space) - 1)
            self._metrics_rl_exploration.inc()
        else:
            # Exploitation: best action
            action_idx = max(range(len(self.action_space)),
                           key=lambda i: self.q_table[state_tuple][i])
            self._metrics_rl_exploitation.inc()

        return action_idx

    def apply_action(self, action_idx: int) -> None:
        """Apply the selected action to the AIMD controller."""
        action = self.action_space[action_idx]

        # Update AIMD parameters
        self.aimd.add = max(1, self.aimd.add + action.add_delta)
        self.aimd.mult = max(0.1, min(0.9, self.aimd.mult + action.mult_delta))

        self.adjustment_count += 1
        self._last_adjustment_time = time.time()
        self._metrics_rl_adjustments.inc()

    def calculate_reward(self, state: RLState, prev_state: Optional[RLState] = None) -> float:
        """Calculate reward for the current state."""
        reward = 0.0

        # Latency reward: prefer lower latency
        if state.latency_ms <= 1000:  # Good latency
            reward += 2.0
        elif state.latency_ms <= 2000:  # Acceptable latency
            reward += 1.0
        else:  # Poor latency
            reward -= 1.0

        # Throughput reward: prefer higher throughput
        if state.throughput >= 100:  # High throughput
            reward += 2.0
        elif state.throughput >= 50:  # Medium throughput
            reward += 1.0
        else:  # Low throughput
            reward -= 1.0

        # Error rate penalty: prefer lower error rates
        if state.error_rate <= 0.01:  # Low error rate
            reward += 1.0
        elif state.error_rate <= 0.05:  # Medium error rate
            reward += 0.0
        else:  # High error rate
            reward -= 2.0

        # Window stability reward: prefer gradual changes
        if prev_state:
            window_change = abs(state.current_window - prev_state.current_window)
            if window_change <= 2:  # Small change
                reward += 0.5
            elif window_change <= 8:  # Medium change
                reward += 0.0
            else:  # Large change
                reward -= 0.5

        return reward

    def update_q_table(self, state: RLState, action_idx: int, reward: float,
                      next_state: RLState) -> None:
        """Update Q-table using Q-learning update rule."""
        state_tuple = self.discretize_state(state)
        next_state_tuple = self.discretize_state(next_state)

        # Find best action for next state
        best_next_action = max(range(len(self.action_space)),
                             key=lambda i: self.q_table[next_state_tuple][i])

        # Q-learning update
        current_q = self.q_table[state_tuple][action_idx]
        next_q = self.q_table[next_state_tuple][best_next_action]

        new_q = current_q + self.learning_rate * (
            reward + self.discount_factor * next_q - current_q
        )

        self.q_table[state_tuple][action_idx] = new_q
        self._metrics_rl_rewards.observe(reward)

    def learn_from_feedback(self, session: str, latency_ms: float, throughput: float,
                          error_rate: float, success: bool = True) -> None:
        """Learn from feedback and potentially adjust AIMD parameters."""
        current_state = self.get_state(session, latency_ms, throughput, error_rate)

        if self.last_state is not None and self.last_action_idx is not None:
            # Calculate reward for previous action
            reward = self.calculate_reward(current_state, self.last_state)

            # Update Q-table
            self.update_q_table(self.last_state, self.last_action_idx, reward, current_state)

        # Select and apply new action
        action_idx = self.select_action(current_state)
        self.apply_action(action_idx)

        # Store for next iteration
        self.last_state = current_state
        self.last_action_idx = action_idx
        self.last_reward = self.calculate_reward(current_state)

    def get_optimal_parameters(self) -> dict[str, float]:
        """Get the current optimal AIMD parameters."""
        return {
            'add': self.aimd.add,
            'mult': self.aimd.mult,
            'learning_rate': self.learning_rate,
            'exploration_rate': self.exploration_rate,
            'total_adjustments': self.adjustment_count
        }

    def save_model(self, filepath: str) -> None:
        """Save the Q-table and parameters to file."""
        # Convert defaultdict to regular dict and tuple keys to strings
        q_table_serializable = {}
        for state_tuple, action_dict in self.q_table.items():
            state_key = str(state_tuple)  # Convert tuple to string
            q_table_serializable[state_key] = dict(action_dict)

        data = {
            'q_table': q_table_serializable,
            'parameters': self.get_optimal_parameters(),
            'timestamp': time.time(),
            'episode_count': self.episode_count
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    def load_model(self, filepath: str) -> None:
        """Load the Q-table and parameters from file."""
        with open(filepath) as f:
            data = json.load(f)

        # Convert string keys back to tuples and reconstruct defaultdict
        q_table_loaded = defaultdict(lambda: defaultdict(float))
        for state_key_str, action_dict in data['q_table'].items():
            # Convert string back to tuple
            state_tuple = tuple(int(x.strip()) for x in state_key_str.strip('()').split(','))
            for action_idx, q_value in action_dict.items():
                q_table_loaded[state_tuple][int(action_idx)] = q_value

        self.q_table = q_table_loaded
        params = data['parameters']
        self.aimd.add = params['add']
        self.aimd.mult = params['mult']
        self.episode_count = data.get('episode_count', 0)


class RLTrainingLoop:
    """Training loop for the RL agent."""

    def __init__(self, agent: AdaptiveWindowRLAgent, episodes: int = 100):
        self.agent = agent
        self.episodes = episodes
        self.training_history: list[dict] = []

    async def simulate_environment(self, episode: int) -> dict[str, float]:
        """Simulate environment interaction for one episode."""
        # Simulate realistic network conditions
        base_latency = 800 + random.gauss(0, 200)  # Base latency with noise
        base_throughput = 75 + random.gauss(0, 25)  # Base throughput with noise
        base_error_rate = 0.02 + random.gauss(0, 0.01)  # Base error rate

        # Simulate session
        session = f"train_session_{episode}"

        # Initial state
        latency = base_latency
        throughput = base_throughput
        error_rate = base_error_rate

        # Run episode steps
        for _step in range(10):
            # Provide feedback to agent
            self.agent.learn_from_feedback(session, latency, throughput, error_rate)

            # Simulate effect of window adjustment on network conditions
            current_window = self.agent.aimd.get(session)

            # Window size affects latency and throughput
            latency_factor = 1.0 + (current_window - 32) / 64  # Optimal around 32
            throughput_factor = 1.0 - abs(current_window - 32) / 128  # Optimal around 32

            latency = base_latency * latency_factor + random.gauss(0, 50)
            throughput = base_throughput * throughput_factor + random.gauss(0, 10)
            error_rate = max(0, base_error_rate + random.gauss(0, 0.005))

            # Small delay to simulate real timing
            await asyncio.sleep(0.01)

        # Get final metrics
        final_window = self.agent.aimd.get(session)
        final_params = self.agent.get_optimal_parameters()

        return {
            'episode': episode,
            'final_window': final_window,
            'final_latency': latency,
            'final_throughput': throughput,
            'final_error_rate': error_rate,
            'add_parameter': final_params['add'],
            'mult_parameter': final_params['mult'],
            'total_adjustments': final_params['total_adjustments']
        }

    async def run_training(self) -> list[dict]:
        """Run the complete training loop."""
        print(f"🚀 Starting RL Training for {self.episodes} episodes...")

        for episode in range(self.episodes):
            if episode % 10 == 0:
                print(f"📊 Episode {episode}/{self.episodes}")

            result = await self.simulate_environment(episode)
            self.training_history.append(result)

            # Decay exploration rate
            self.agent.exploration_rate = max(0.01, self.agent.exploration_rate * 0.995)

        print("✅ RL Training completed!")
        return self.training_history

    def get_training_summary(self) -> dict[str, float]:
        """Get summary statistics from training."""
        if not self.training_history:
            return {}

        latencies = [h['final_latency'] for h in self.training_history]
        throughputs = [h['final_throughput'] for h in self.training_history]
        error_rates = [h['final_error_rate'] for h in self.training_history]
        adjustments = [h['total_adjustments'] for h in self.training_history]

        return {
            'avg_final_latency': sum(latencies) / len(latencies),
            'avg_final_throughput': sum(throughputs) / len(throughputs),
            'avg_final_error_rate': sum(error_rates) / len(error_rates),
            'total_adjustments': sum(adjustments),
            'training_episodes': len(self.training_history)
        }


async def main():
    """Main function to demonstrate RL training."""
    # Create AIMD controller
    aimd = AIMDController()

    # Create RL agent
    agent = AdaptiveWindowRLAgent(aimd)

    # Create training loop
    trainer = RLTrainingLoop(agent, episodes=50)

    # Run training
    await trainer.run_training()

    # Get summary
    summary = trainer.get_training_summary()

    print("\n📈 Training Summary:")
    print(f"Average Final Latency: {summary['avg_final_latency']:.2f}ms")
    print(f"Average Final Throughput: {summary['avg_final_throughput']:.2f} req/s")
    print(f"Average Final Error Rate: {summary['avg_final_error_rate']:.4f}")
    print(f"Total Adjustments: {summary['total_adjustments']}")

    # Save the trained model
    agent.save_model("rl_window_model.json")
    print("💾 Model saved to rl_window_model.json")

    return agent, summary


if __name__ == "__main__":
    asyncio.run(main())
