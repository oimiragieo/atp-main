from typing import Any


def evaluate(tasks: list[dict[str, Any]], picker, ground_truth: dict[str, str]) -> dict[str, Any]:
    """Evaluate a picker(candidate_list)->name across tasks.

    tasks: [{"id":str, "candidates":[{"name":...,"score":float}]}]
    ground_truth: {task_id: best_name}
    """
    correct = 0
    total = 0
    choices: list[tuple[str, str]] = []
    for t in tasks:
        total += 1
        cands = sorted(t["candidates"], key=lambda c: c["score"], reverse=True)
        pick = picker(cands)
        choices.append((t["id"], pick))
        if ground_truth.get(t["id"]) == pick:
            correct += 1
    acc = correct / max(1, total)
    return {"accuracy": acc, "choices": choices}
