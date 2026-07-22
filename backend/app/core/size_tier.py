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
