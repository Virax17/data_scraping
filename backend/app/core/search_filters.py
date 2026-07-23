"""Region targeting helpers — pure functions, no I/O.

location_strings() builds Apollo `person_locations` values from a target
country/city pair. matches_region() is a post-sweep backstop for when a
preview DOES carry real location data — but Apollo's free people-search
preview only exposes `has_city`/`has_state`/`has_country` booleans, never the
actual values (those are paid/reveal-tier fields), so in practice every
preview's city/state/country come through as None. The check is therefore
lenient on missing data on both sides (country and city): it only drops a
person when we have a real value that actually mismatches the target,
otherwise it defers entirely to Apollo's own server-side person_locations
filtering, which already does the real narrowing."""

from __future__ import annotations


def location_strings(country: str | None, city: str | None) -> list[str]:
    """Build the Apollo `person_locations` filter values for a target region.
    Apollo accepts free-text location strings such as "Houston, US" or
    "United States" — city+country pairs narrow further than country alone."""
    country = (country or "").strip()
    city = (city or "").strip()
    if not country and not city:
        return []
    if city and country:
        return [f"{city}, {country}"]
    return [city or country]


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def matches_region(emp_city: str | None, emp_state: str | None, emp_country: str | None,
                   target_country: str | None, target_city: str | None) -> bool:
    """True when a stored employee preview is in the targeted region, or when
    we simply don't have enough data on the preview to tell (Apollo's free
    preview never carries real location values). Only drops someone when a
    real value is present AND it actually mismatches the target — missing
    data on either side always passes, deferring to Apollo's own
    person_locations filtering."""
    target_country = _norm(target_country)
    target_city = _norm(target_city)
    if not target_country and not target_city:
        return True

    if target_country:
        country = _norm(emp_country)
        if country and target_country not in country and country not in target_country:
            return False

    if target_city:
        city = _norm(emp_city)
        state = _norm(emp_state)
        if city and target_city not in city and city not in target_city:
            return False
        if not city and state and target_city not in state and state not in target_city:
            return False

    return True
