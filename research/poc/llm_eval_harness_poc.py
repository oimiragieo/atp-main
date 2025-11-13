"""LLM Evaluation Harness POC
Defines a small task suite (classification + math), runs simulated adapter/model responses,
computes accuracy and simple regression comparison against a stored baseline.
Outputs OK line if accuracy >= threshold and no regression > tolerance.
"""

import ast
import json
import os
import random

random.seed(0)

TASKS = [
    {"id": "cls1", "type": "cls", "input": "sky color", "gold": "blue"},
    {"id": "cls2", "type": "cls", "input": "grass color", "gold": "green"},
    {"id": "math1", "type": "math", "input": "2+3*4", "gold": "14"},
    {"id": "math2", "type": "math", "input": "7*6", "gold": "42"},
]
BASELINE_FILE = "eval_baseline.json"


class FakeModel:
    def __init__(self, accuracy_noise=0.0):
        self.accuracy_noise = accuracy_noise

    def infer(self, task):
        if task["type"] == "cls":
            # 95% chance correct
            if random.random() < 0.95 - self.accuracy_noise:
                return task["gold"]
            return "unknown"
        if task["type"] == "math":
            # parse simple arithmetic expression safely
            try:
                node = ast.parse(task["input"], mode="eval")
            except Exception:
                return "err"
            try:
                return str(_safe_eval(node.body))
            except Exception:
                return "err"
        return "unknown"


def _safe_eval(node):
    """Evaluate a limited arithmetic AST node supporting +,-,*,/,** and parentheses with numbers.
    Raises ValueError for any disallowed construct."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
        return (
            _safe_eval(node.left) + _safe_eval(node.right)
            if isinstance(node.op, ast.Add)
            else _safe_eval(node.left) - _safe_eval(node.right)
            if isinstance(node.op, ast.Sub)
            else _safe_eval(node.left) * _safe_eval(node.right)
            if isinstance(node.op, ast.Mult)
            else _safe_eval(node.left) / _safe_eval(node.right)
            if isinstance(node.op, ast.Div)
            else _safe_eval(node.left) ** _safe_eval(node.right)
        )
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        val = _safe_eval(node.operand)
        return val if isinstance(node.op, ast.UAdd) else -val
    if isinstance(node, ast.Num):  # py<3.8
        return node.n
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    raise ValueError("disallowed expression")


def run_eval(model: FakeModel):
    results = []
    correct = 0
    for t in TASKS:
        out = model.infer(t)
        ok = out == t["gold"]
        correct += 1 if ok else 0
        results.append({"id": t["id"], "ok": ok})
    acc = correct / len(TASKS)
    return {"accuracy": acc, "results": results}


def load_baseline():
    if os.path.exists(BASELINE_FILE):
        with open(BASELINE_FILE) as f:
            return json.load(f)
    return None


def save_baseline(acc):
    with open(BASELINE_FILE, "w") as f:
        json.dump({"accuracy": acc}, f)


if __name__ == "__main__":
    model = FakeModel()
    res = run_eval(model)
    baseline = load_baseline()
    threshold = 0.75
    regression_tolerance = 0.05
    if baseline is None:
        save_baseline(res["accuracy"])
        print(f"OK: llm eval harness POC established baseline acc={round(res['accuracy'], 3)}")
    else:
        regressed = res["accuracy"] + regression_tolerance < baseline["accuracy"]
        if res["accuracy"] >= threshold and not regressed:
            print(f"OK: llm eval harness POC passed acc={round(res['accuracy'], 3)} baseline={baseline['accuracy']}")
        else:
            print(f"FAIL: llm eval harness POC acc={res['accuracy']} baseline={baseline['accuracy']}")
