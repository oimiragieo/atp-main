"""RL Auto-Tuning POC
Adjusts token window based on reward (latency adherence + cost). Uses simple Q-learning over discrete actions.
"""

import random

random.seed(2025)
ACTIONS = [-50, 0, 50]  # adjust window size delta


def simulate(episodes=60, start_window=500):
    q = {(w, a): 0 for w in range(300, 801, 50) for a in ACTIONS}
    window = start_window
    for _ep in range(episodes):
        state = 50 * round(window / 50)
        action = max(ACTIONS, key=lambda a: q[(state, a)] if (state, a) in q else 0)
        if random.random() < 0.2:
            action = random.choice(ACTIONS)
        new_window = min(800, max(300, window + action))
        # synthetic reward: prefer ~650 window; penalty for deviation and size
        reward = -abs(650 - new_window) / 100 - new_window / 2000
        q[(state, action)] = q.get((state, action), 0) + 0.1 * (reward - q.get((state, action), 0))
        window = new_window
    return window


if __name__ == "__main__":
    final = simulate()
    if 560 <= final <= 740:
        print(f"OK: rl auto-tuning windows POC passed final_window={final}")
    else:
        print("FAIL: rl auto-tuning windows POC", final)
