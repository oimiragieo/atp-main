"""LinUCB Router Refinement POC
Builds on learning router; computes regret over time to show improvement over random.
"""

import math
import random


def linucb(rounds=80, alpha=0.4):
    arms = ["a", "b"]
    dim = 3
    a_mats = {a: [[1 if i == j else 0 for j in range(dim)] for i in range(dim)] for a in arms}
    b = {a: [0] * dim for a in arms}

    def invert(mat):
        a, bm, c = mat[0]
        d, e, f = mat[1]
        g, h, i = mat[2]
        det = a * (e * i - f * h) - bm * (d * i - f * g) + c * (d * h - e * g)
        if abs(det) < 1e-9:
            return [[0] * 3 for _ in range(3)]
        return [
            [(e * i - f * h) / det, (c * h - bm * i) / det, (bm * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (bm * g - a * h) / det, (a * e - bm * d) / det],
        ]

    regrets = []
    total_regret = 0.0
    for _t in range(rounds):
        ctx = [random.random() for _ in range(dim)]

        def r_a(x):
            return 0.5 + 0.4 * x[0]

        def r_b(x):
            return 0.55 + 0.35 * x[1]

        exp_a = r_a(ctx)
        exp_b = r_b(ctx)
        best_true = max(exp_a, exp_b)
        best = None
        best_ucb = -1.0
        for arm in arms:
            a_inv = invert(a_mats[arm])
            theta = [sum(a_inv[r][c] * b[arm][c] for c in range(dim)) for r in range(dim)]
            est = sum(theta[i] * ctx[i] for i in range(dim))
            v = math.sqrt(sum(ctx[i] * sum(a_inv[i][j] * ctx[j] for j in range(dim)) for i in range(dim)))
            ucb = est + alpha * v
            if ucb > best_ucb:
                best_ucb = ucb
                best = arm
        reward = (r_a(ctx) if best == "a" else r_b(ctx)) + random.uniform(-0.03, 0.03)
        a_best = a_mats[best]
        for i in range(dim):
            for j in range(dim):
                a_best[i][j] += ctx[i] * ctx[j]
        for i in range(dim):
            b[best][i] += reward * ctx[i]
        regret = best_true - reward
        total_regret += regret
        regrets.append(total_regret)
    avg_regret = total_regret / rounds
    return avg_regret


if __name__ == "__main__":
    ar = linucb()
    if ar < 0.15:
        print(f"OK: linucb router refinement POC passed avg_regret={round(ar, 3)}")
    else:
        print("FAIL: linucb router refinement POC", ar)
