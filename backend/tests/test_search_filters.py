from app.core.search_filters import location_strings, matches_region


def test_location_strings_none():
    assert location_strings(None, None) == []
    assert location_strings("", "") == []


def test_location_strings_country_only():
    assert location_strings("United States", None) == ["United States"]


def test_location_strings_city_only():
    assert location_strings(None, "Houston") == ["Houston"]


def test_location_strings_city_and_country():
    assert location_strings("United States", "Houston") == ["Houston, United States"]


def test_matches_region_no_target_always_true():
    assert matches_region(None, None, None, None, None) is True
    assert matches_region("Paris", None, "France", None, None) is True


def test_matches_region_country_match():
    assert matches_region("Houston", "Texas", "United States", "United States", None) is True


def test_matches_region_country_mismatch():
    assert matches_region("Paris", None, "France", "United States", None) is False


def test_matches_region_missing_country_is_lenient():
    # Apollo's free preview never carries a real country value (only a
    # has_country flag) — missing data must not drop everyone, or region
    # targeting silently zeroes out every sweep. Defer to Apollo's own filter.
    assert matches_region("Houston", "Texas", None, "United States", None) is True


def test_matches_region_city_match():
    assert matches_region("Houston", "Texas", "United States",
                          "United States", "Houston") is True


def test_matches_region_city_mismatch():
    assert matches_region("Dallas", "Texas", "United States",
                          "United States", "Houston") is False


def test_matches_region_city_missing_falls_back_to_state():
    # No city on the preview but state matches the target city string loosely
    assert matches_region(None, "Houston", "United States",
                          "United States", "Houston") is True


def test_matches_region_city_missing_and_no_state_lenient():
    # Neither city nor state on the preview — country already matched via
    # Apollo's own filter, so don't drop it over missing granularity.
    assert matches_region(None, None, "United States",
                          "United States", "Houston") is True


def test_matches_region_case_insensitive():
    assert matches_region("HOUSTON", "TX", "UNITED STATES",
                          "united states", "houston") is True


def test_matches_region_all_fields_missing_apollo_free_preview_shape():
    # Regression: Apollo's free people-search preview returns only
    # has_city/has_state/has_country booleans, never real values — every
    # field is None. A target region must not drop everyone in this shape.
    assert matches_region(None, None, None, "United States", "Odessa") is True
