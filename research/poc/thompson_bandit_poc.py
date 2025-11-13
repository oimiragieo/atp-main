import random
from dataclasses import dataclass


@dataclass
class Arm:
    name: str
    alpha: float = 1.0
    beta: float = 1.0


def select_arm(arms: list[Arm]) -> int:
    draws = [random.gammavariate(a.alpha, 1) / (random.gammavariate(a.beta, 1)) for a in arms]
    return max(range(len(arms)), key=lambda i: draws[i])


def update(arm: Arm, reward: int):
    if reward:
        arm.alpha += 1
    else:
        arm.beta += 1


def simulate(true_ps: list[float], steps: int = 200, seed: int = 42) -> tuple[list[Arm], int]:
    random.seed(seed)
    arms = [Arm(f"a{i}") for i in range(len(true_ps))]
    wins = 0
    for _ in range(steps):
        i = select_arm(arms)
        reward = 1 if random.random() < true_ps[i] else 0
        if i == max(range(len(true_ps)), key=lambda j: true_ps[j]):
            wins += 1
        update(arms[i], reward)
    return arms, wins
