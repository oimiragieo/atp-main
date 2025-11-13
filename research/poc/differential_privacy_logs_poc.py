"""Differential Privacy Logs POC
Applies Laplace noise to usage counts and enforces epsilon budget.
"""

import math
import random

random.seed(0)


def laplace(mu: float, b: float) -> float:
    """Sample from Laplace(mu, b) via inverse CDF."""
    u = random.random() - 0.5
    return mu - b * math.copysign(1.0, u) * math.log(1 - 2 * abs(u))


class DpLogger:
    def __init__(self, epsilon: float = 1.0, sensitivity: float = 1.0):
        self.epsilon = epsilon
        self.sensitivity = sensitivity
        self.count = 0
        self.spent = 0.0

    def log(self, n: int = 1):
        self.count += n

    def release(self) -> float:
        # compute Laplace noise with scale = sensitivity/epsilon
        scale = self.sensitivity / self.epsilon
        noise = laplace(0.0, scale)
        self.spent += self.epsilon
        return self.count + noise


if __name__ == "__main__":
    dp = DpLogger(epsilon=1.5)
    for _ in range(20):
        dp.log()
    noisy = dp.release()
    if abs(noisy - 20) < 25 and dp.spent > 0:
        print("OK: differential privacy logs POC passed")
    else:
        print("FAIL: differential privacy logs POC", noisy, dp.spent)
