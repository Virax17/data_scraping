"""Deterministic-layer tests against the real generated reference data."""

from app.core.classify import classify_company, load_icp, load_targeting
from app.core.dedup import dedup_contacts, domain_from_website
from app.core.size_tier import reconcile_with_sweep, size_tier


def test_domain_from_website():
    assert domain_from_website("https://www.example.com/about") == "example.com"
    assert domain_from_website("example.com") == "example.com"
    assert domain_from_website("") is None
    assert domain_from_website(None) is None


def test_reference_data_loads():
    targeting = load_targeting()
    assert len(targeting) == 7
    icp = load_icp()
    assert "Oil & Gas" in icp["industries"]


def test_classify_icp_match_epc():
    result = classify_company("Larsen & Toubro (L&T)")
    assert result["confidence"] == "icp_match"
    assert result["customer_type"] == "EPC / Project Engineering Organizations"


def test_classify_keyword_end_user():
    result = classify_company("Acme Refinery Corp", "oil & gas refinery operator",
                              icp_data={})
    assert result["customer_type"] == "End User (Plant / Facility Owner)"


def test_classify_ambiguous():
    result = classify_company("Totally Unknown Widgets LLC", "", icp_data={})
    assert result["customer_type"] is None
    assert result["confidence"] == "ambiguous"


def test_classify_generic_sector_word_in_name_alone_does_not_match():
    # Regression: "Jones Power" (a civil-construction/site-prep contractor,
    # not a power-plant owner) used to false-match End User purely because
    # "power" appeared in its own name. Generic sector words must only be
    # checked against industry_text, never the company name.
    result = classify_company("Jones Power", "civil construction and site-prep contractor",
                              icp_data={})
    assert result["customer_type"] != "End User (Plant / Facility Owner)"


def test_classify_industry_tag_utilities_is_end_user():
    result = classify_company("Example Utility Co", "utilities", icp_data={},
                              industry="utilities")
    assert result["customer_type"] == "End User (Plant / Facility Owner)"
    assert result["confidence"] == "industry_tag_match"


def test_classify_brand_name_substring_no_longer_false_matches():
    # Regression: a bare "brock" keyword trigger used to catch "Brock
    # Solutions" (an unrelated automation/controls company), which was
    # actually meant to catch "Brock Group" (a turnaround/scaffolding
    # services company). Brand recognition now lives only in the ICP list,
    # which matches full names, not substrings -- so an unrelated company
    # whose name merely contains a brand fragment must not false-match.
    result = classify_company("Brock Solutions", "industrial automation and controls software",
                              icp_data={})
    assert result["customer_type"] != "Service Providers / Turnaround & Bolting Specialists"


def test_size_tier_boundaries():
    assert size_tier(10) == "micro"
    assert size_tier(200) == "small"
    assert size_tier(201) == "mid"
    assert size_tier(5001) == "enterprise"
    assert size_tier(None) is None


def test_reconcile_with_sweep_downtiers_multinational_headcount_mismatch():
    # Regression: Apollo's org.estimated_num_employees can reflect a
    # multinational parent's global headcount (e.g. Nexans ~25,700 globally)
    # even when the resolved domain is really a small regional/US
    # subsidiary -- confirmed via real-world research to inflate size_tier
    # (and, via reveal_cap_by_size_tier, the reveal budget) far past what
    # that specific office supports. A stark mismatch between the org-level
    # figure and this run's own free sweep at that exact domain should
    # down-tier to what the sweep actually supports.
    assert reconcile_with_sweep("enterprise", employees_found=8) == "micro"
    assert reconcile_with_sweep("large", employees_found=5) == "micro"


def test_reconcile_with_sweep_leaves_small_gap_uncorrected():
    # A one-tier gap is well within normal Apollo indexing incompleteness
    # for a genuinely large company -- shouldn't be corrected.
    assert reconcile_with_sweep("large", employees_found=500) == "large"


def test_reconcile_with_sweep_ignores_non_large_tiers():
    # micro/small/mid aren't at risk of the multinational-parent-headcount
    # failure mode (there's no larger "true" tier to have been inflated
    # from), so leave them untouched regardless of sweep count.
    assert reconcile_with_sweep("small", employees_found=0) == "small"
    assert reconcile_with_sweep(None, employees_found=0) is None


def test_dedup_by_linkedin():
    contacts = [
        {"linkedin_url": "linkedin.com/in/jdoe", "company_name": "Acme"},
        {"linkedin_url": "linkedin.com/in/jdoe", "company_name": "Acme Subsidiary"},
    ]
    deduped = dedup_contacts(contacts)
    assert len(deduped) == 1
    assert "Acme Subsidiary" in deduped[0]["_dedup_companies"]


def test_dedup_by_email_fallback():
    contacts = [{"email": "jane@acme.com"}, {"email": "JANE@ACME.COM"}]
    assert len(dedup_contacts(contacts)) == 1


def test_dedup_by_apollo_id_when_name_missing():
    # Regression: Apollo's free preview never returns a real full_name, so
    # every unrevealed person at a company shares an empty name+company key
    # and used to collapse into one row. apollo_id must keep them distinct.
    contacts = [
        {"apollo_id": "p1", "full_name": None, "company_name": "Acme"},
        {"apollo_id": "p2", "full_name": None, "company_name": "Acme"},
        {"apollo_id": "p3", "full_name": None, "company_name": "Acme"},
    ]
    deduped = dedup_contacts(contacts)
    assert len(deduped) == 3
    assert {c["apollo_id"] for c in deduped} == {"p1", "p2", "p3"}


def test_dedup_by_apollo_id_still_collapses_same_person():
    contacts = [
        {"apollo_id": "p1", "full_name": None, "company_name": "Acme"},
        {"apollo_id": "p1", "full_name": None, "company_name": "Acme"},
    ]
    assert len(dedup_contacts(contacts)) == 1
