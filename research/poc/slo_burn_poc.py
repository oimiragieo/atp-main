def burn_rate(
    error_counts: list[int], request_counts: list[int], window_minutes: int, slo_error_budget: float
) -> tuple[float, bool]:
    """Compute error budget burn and alert boolean.

    error_counts, request_counts: aligned series per minute.
    slo_error_budget: e.g., 0.01 for 99% SLO.
    Returns (burn_rate, alert) where alert if burn_rate > 1 over the window.
    """
    errors = sum(error_counts)
    reqs = max(1, sum(request_counts))
    observed_error_rate = errors / reqs
    # budget per minute proportion
    budget_per_min = slo_error_budget
    # burn rate as multiple of allowed budget
    br = observed_error_rate / max(1e-9, budget_per_min)
    return br, br > 1.0
