from dataclasses import dataclass


@dataclass
class Candidate:
    name: str
    confidence: float  # 0..1
    usd_micros: int


def select(
    ch: list[Candidate], min_conf: float = 0.7, near_eps: float = 0.02
) -> tuple[Candidate | None, Candidate | None, bool]:
    """Return (champion, challenger, escalated).

    Champion: highest confidence (tie-break by lower cost). Escalate if champion below min_conf.
    If challenger within near_eps confidence of champion and cheaper, escalate to run both.
    """
    if not ch:
        return None, None, False
    scored = sorted(ch, key=lambda c: (-c.confidence, c.usd_micros))
    champion = scored[0]
    challenger = scored[1] if len(scored) > 1 else None
    escalated = champion.confidence < min_conf
    # If challenger within small delta on score but cheaper, consider escalate double-run
    if challenger:
        if (champion.confidence - challenger.confidence) <= near_eps and (challenger.usd_micros < champion.usd_micros):
            escalated = True
    return champion, challenger, escalated
