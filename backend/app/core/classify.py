"""Deterministic company classification: ICP list lookup -> keyword rubric ->
explicit ambiguous state. The result is *context* fed to the LLM judge, never
a final gate — the judge prompt receives it as a hint."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

REFERENCE_DIR = Path(__file__).parent.parent / "reference_data"


# Apollo's org `industry` field is a small, closed taxonomy (the same ~dozen
# values recur across any customer's export) -- an exact match against it is
# high-precision and generalizes to any future company Apollo tags with the
# same value, unlike matching against free text. Only values unambiguous
# enough to map to exactly one customer type belong here. Both "oil & energy"
# and, surprisingly, "construction" turned out too coarse to hardcode here:
# real-world audit data showed "construction"-tagged companies splitting
# across EPC firms, civil/earthwork contractors, pipeline maintenance
# contractors, and even a plumbing-fittings OEM -- Apollo's tag reflects a
# broad economic sector, not a Tritorc-specific customer-type distinction, so
# those must fall through to the (weaker, but more specific) keyword rubric
# below instead of a blanket tag mapping.
_INDUSTRY_TAG_MAP: dict[str, str] = {
    "utilities": "End User (Plant / Facility Owner)",
}

# Matched against the fuller industry_text blob (industry + description +
# keywords). Deliberately excludes generic single-sector words ("power",
# "steel", "cement", "mining", "lng", ...): real companies' Apollo keyword
# tags routinely name every sector they SERVE, not just one they OWN/OPERATE
# assets in (an EPC contractor's keywords mention "power", "mining", "oil and
# gas" as project types it builds, not sectors it operates in) -- so those
# words match too many unrelated customer types to be trustworthy signals.
# Only phrases specific enough to describe a role/scope, not just a sector,
# are listed.
_CLASSIFICATION_TRIGGERS: list[tuple[str, list[str]]] = [
    (
        "End User (Plant / Facility Owner)",
        ["oil & gas", "oil and gas", "utilities", "utility", "refinery",
         "refineries", "refining", "asset owner", "plant owner", "facility owner"],
    ),
    (
        "Industrial Equipment Rental Companies",
        ["equipment rental", "tool rental", "rental fleet"],
    ),
    (
        "EPC / Project Engineering Organizations",
        ["epc", "engineering procurement construction", "project engineering"],
    ),
    (
        "Service Providers / Turnaround & Bolting Specialists",
        ["turnaround", "shutdown", "bolting", "flange management", "hot tap",
         "hot-tapping", "pipeline integrity", "integrity management",
         "pipeline rehabilitation"],
    ),
    (
        "Mechanical / Maintenance Contractors",
        ["mechanical contractor", "maintenance services", "field services"],
    ),
    (
        "OEMs / Manufacturers (Equipment, Packages, Skids)",
        ["manufacturer", "oem", "equipment packages", "skid package", "skids",
         "fabrication", "fabricator"],
    ),
]

_ICP_CATEGORY_TO_CUSTOMER_TYPE: list[tuple[str, str]] = [
    ("service", "Service Providers / Turnaround & Bolting Specialists"),
    ("epc", "EPC / Project Engineering Organizations"),
    ("oem", "OEMs / Manufacturers (Equipment, Packages, Skids)"),
    ("manufacturer", "OEMs / Manufacturers (Equipment, Packages, Skids)"),
    ("rental", "Industrial Equipment Rental Companies"),
    ("owner", "End User (Plant / Facility Owner)"),
    ("operator", "End User (Plant / Facility Owner)"),
    ("plant", "End User (Plant / Facility Owner)"),
    ("producer", "End User (Plant / Facility Owner)"),
    ("shipyard", "End User (Plant / Facility Owner)"),
]


@lru_cache(maxsize=1)
def load_targeting() -> dict:
    return json.loads((REFERENCE_DIR / "targeting.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_icp() -> dict:
    return json.loads((REFERENCE_DIR / "icp_companies.json").read_text(encoding="utf-8"))


def _find_in_icp(company_name: str, icp_data: dict) -> tuple[str, str, str] | None:
    name_norm = company_name.strip().lower()
    for industry, categories in icp_data.get("industries", {}).items():
        for category, companies in categories.items():
            for entry in companies:
                entry_norm = entry.strip().lower()
                if name_norm == entry_norm or name_norm in entry_norm or entry_norm in name_norm:
                    return industry, category, entry
    return None


def classify_company(company_name: str, industry_text: str = "",
                     icp_data: dict | None = None, industry: str | None = None) -> dict:
    """Returns {customer_type, confidence, matched_via, candidates}.
    customer_type=None means ambiguous — the judge prompt handles it.

    Named-brand recognition (specific companies, e.g. "Larsen & Toubro",
    "Brock Group") is handled entirely by the ICP list below, which matches
    against the full curated company name, never a bare substring. The
    keyword rubric only ever matches against industry_text (Apollo's
    industry/description/keywords fields) — never the company's own name —
    because generic sector words ("power", "steel", ...) routinely appear
    inside unrelated companies' brand names (e.g. "Jones Power", a
    civil-construction contractor with no power-plant ownership) and would
    otherwise false-match on pure coincidence.

    `industry` is Apollo's bare org industry tag, if the caller has it
    separately from the fuller industry_text blob — checked first against
    a small closed-taxonomy map since it's the highest-precision signal
    available; falls through to the keyword rubric on industry_text when
    the tag isn't one of the unambiguous ones (or wasn't passed)."""
    icp_data = icp_data if icp_data is not None else load_icp()

    icp_hit = _find_in_icp(company_name, icp_data)
    if icp_hit:
        industry_cat, category, matched_name = icp_hit
        for substr, customer_type in _ICP_CATEGORY_TO_CUSTOMER_TYPE:
            if substr in category.lower():
                return {
                    "customer_type": customer_type,
                    "confidence": "icp_match",
                    "matched_via": f"ICP list: '{matched_name}' under {industry_cat} / {category}",
                    "candidates": [customer_type],
                }

    tag_hit = _INDUSTRY_TAG_MAP.get((industry or "").strip().lower())
    if tag_hit:
        return {"customer_type": tag_hit, "confidence": "industry_tag_match",
                "matched_via": f"Apollo industry tag '{industry}' maps to '{tag_hit}'",
                "candidates": [tag_hit]}

    haystack = industry_text.lower()
    matches = [ct for ct, triggers in _CLASSIFICATION_TRIGGERS
               if any(t in haystack for t in triggers)]

    if len(matches) == 1:
        return {"customer_type": matches[0], "confidence": "keyword_match",
                "matched_via": f"keyword rubric matched '{matches[0]}'",
                "candidates": matches}

    return {"customer_type": None, "confidence": "ambiguous",
            "matched_via": ("multiple keyword triggers matched" if matches
                            else "no ICP or keyword signal found"),
            "candidates": matches}
