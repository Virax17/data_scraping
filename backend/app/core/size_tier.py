"""Employee-count -> size tier. Tier bounds/caps come from live settings."""

from __future__ import annotations

DEFAULT_BOUNDS = {
    "micro": (0, 49),
    "small": (50, 200),
    "mid": (201, 1000),
    "large": (1001, 5000),
    "enterprise": (5001, None),
}


def size_tier(employee_count: int | None, bounds: dict | None = None) -> str | None:
    if employee_count is None:
        return None
    bounds = bounds or DEFAULT_BOUNDS
    for tier, (lo, hi) in bounds.items():
        lo_hi = (lo, hi) if not isinstance(lo, list) else tuple(lo)
        if employee_count >= lo_hi[0] and (lo_hi[1] is None or employee_count <= lo_hi[1]):
            return tier
    return None


_TIER_RANK = ["micro", "small", "mid", "large", "enterprise"]


def reconcile_with_sweep(tier: str | None, employees_found: int,
                         bounds: dict | None = None) -> str | None:
    """Down-tier a `large`/`enterprise` classification when this run's own
    free, unfiltered people-sweep at the company's exact domain turns up far
    fewer people than that tier implies.

    Apollo's org.estimated_num_employees is a single global figure — for a
    multinational, it can reflect the ultimate parent's headcount even when
    the resolved org record actually corresponds to a small regional/US
    subsidiary domain. That inflates size_tier (and, via
    reveal_cap_by_size_tier, the reveal budget) far past what the specific
    office being prospected can support. The sweep is real, run-specific,
    and free, so a stark mismatch is a strong, generalizable signal of this
    exact failure mode — not a one-off — hence the >=2-tier gap threshold
    (a one-tier gap is well within normal Apollo indexing incompleteness for
    a genuinely large company and shouldn't trigger a correction)."""
    if tier not in ("large", "enterprise"):
        return tier
    sweep_tier = size_tier(employees_found, bounds)
    if sweep_tier is None:
        return tier
    if _TIER_RANK.index(sweep_tier) <= _TIER_RANK.index(tier) - 2:
        return sweep_tier
    return tier
