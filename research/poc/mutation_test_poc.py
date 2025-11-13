"""Minimal mutation testing POC.

This POC demonstrates two quick, deterministic mutation trials that run in <1s:

- trial_synthetic: run a tiny function and its test suite, mutate an operator and
  confirm at least one mutant is killed by the tests.
- trial_fragment_checksum: mutate the fragmentation checksum function so that a
  corrupt fragment is no longer detected, and verify that our check fails (mutant
  is killed).

The goal is to show feasibility and speed rather than adopt a full mutation runner.
We keep this as a tool so CI can opt-in later.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


def _synthetic_cmp(a: int, b: int) -> bool:
    return a == b


def _synthetic_tests(fn: Callable[[int, int], bool]) -> None:
    assert fn(1, 1) is True
    assert fn(2, 3) is False


@dataclass
class MutationResult:
    name: str
    mutants_total: int
    mutants_killed: int


def trial_synthetic() -> MutationResult:
    # Baseline: tests pass
    _synthetic_tests(_synthetic_cmp)

    # Mutant: flip comparison to always True
    def mutant_always_true(a: int, b: int) -> bool:  # noqa: ARG001 - fixed signature
        return True

    killed = 0
    total = 1
    try:
        _synthetic_tests(mutant_always_true)
    except AssertionError:
        killed += 1
    return MutationResult(name="synthetic", mutants_total=total, mutants_killed=killed)


def trial_fragment_checksum() -> MutationResult:
    # Baseline: corrupt checksum is detected by reassembler
    import router_service.fragmentation as frag_mod
    from router_service.fragmentation import Reassembler, fragment_frame
    from router_service.frame import Frame, Meta, Payload, Window

    def make_frame(text: str) -> Frame:
        return Frame(
            v=1,
            session_id="s",
            stream_id="st",
            msg_seq=0,
            frag_seq=0,
            flags=["SYN"],
            qos="gold",
            ttl=5,
            window=Window(max_parallel=4, max_tokens=10000, max_usd_micros=1_000_000),
            meta=Meta(task_type="qa"),
            payload=Payload(type="agent.result.partial", content={"text": text}),
        )

    base = make_frame("X" * 300)
    frags = fragment_frame(base, max_fragment_size=100)
    assert len(frags) > 1
    # Corrupt first fragment checksum
    frags[0].payload.checksum = "deadbeef"
    r = Reassembler()
    corruption_detected = False
    for f in frags:
        try:
            _ = r.push(f)
        except ValueError:
            corruption_detected = True
            break
    assert corruption_detected  # baseline behavior

    # Mutate: break checksum function to always return matching value, hiding corruption
    original = frag_mod._compute_checksum
    frag_mod._compute_checksum = lambda _text: "deadbeef"  # type: ignore[assignment]
    try:
        # Re-run with same fragments but normalize their checksums to the mutated value
        for f in frags:
            f.payload.checksum = "deadbeef"
        # detection should now fail -> test kills mutant
        r2 = Reassembler()
        corruption_detected2 = False
        for f in frags:
            try:
                _ = r2.push(f)
            except ValueError:
                corruption_detected2 = True
                break
        killed = 1 if not corruption_detected2 else 0
        return MutationResult(name="fragment_checksum", mutants_total=1, mutants_killed=killed)
    finally:
        frag_mod._compute_checksum = original  # type: ignore[assignment]


def run_all_trials() -> dict[str, MutationResult]:
    results = {}
    for trial in (trial_synthetic, trial_fragment_checksum):
        res = trial()
        results[res.name] = res
    return results


def main() -> None:
    results = run_all_trials()
    total = sum(r.mutants_total for r in results.values())
    killed = sum(r.mutants_killed for r in results.values())
    print(
        {
            "trials": {k: r.__dict__ for k, r in results.items()},
            "summary": {"mutants_total": total, "mutants_killed": killed},
        }
    )


if __name__ == "__main__":
    main()
