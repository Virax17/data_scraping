"""Deterministic-layer tests against the real generated reference data."""

from app.core.classify import classify_company, load_icp, load_targeting
from app.core.dedup import dedup_contacts, domain_from_website
from app.core.size_tier import size_tier


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


def test_size_tier_boundaries():
    assert size_tier(10) == "micro"
    assert size_tier(200) == "small"
    assert size_tier(201) == "mid"
    assert size_tier(5001) == "enterprise"
    assert size_tier(None) is None


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
