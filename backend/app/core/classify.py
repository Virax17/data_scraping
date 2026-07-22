"""Deterministic company classification: ICP list lookup -> keyword rubric ->
explicit ambiguous state. The result is *context* fed to the LLM judge, never
a final gate — the judge prompt receives it as a hint."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

REFERENCE_DIR = Path(__file__).parent.parent / "reference_data"

_CLASSIFICATION_TRIGGERS: list[tuple[str, list[str]]] = [
    (
        "End User (Plant / Facility Owner)",
        ["oil & gas", "oil and gas", "power", "cement", "steel", "fertilizer",
         "mining", "refinery", "refineries", "lng", "asset owner", "operator",
         "plant owner", "facility owner"],
    ),
    (
        "Industrial Equipment Rental Companies",
        ["equipment rental", "tool rental", "rental fleet"],
    ),
    (
        "EPC / Project Engineering Organizations",
        ["epc", "engineering procurement construction", "project engineering",
         "l&t", "larsen & toubro", "technip", "mcdermott", "saipem", "petrofac"],
    ),
    (
        "Service Providers / Turnaround & Bolting Specialists",
        ["turnaround", "shutdown", "bolting", "flange management",
         "enermech", "bilfinger", "brock", "sparrows"],
    ),
    (
        "Mechanical / Maintenance Contractors",
        ["mechanical contractor", "maintenance services", "field services"],
    ),
    (
        "OEMs / Manufacturers (Equipment, Packages, Skids)",
        ["manufacturer", "oem", "equipment packages", "skid package", "skids"],
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
                     icp_data: dict | None = None) -> dict:
    """Returns {customer_type, confidence, matched_via, candidates}.
    customer_type=None means ambiguous — the judge prompt handles it."""
    icp_data = icp_data if icp_data is not None else load_icp()
    haystack = f"{company_name} {industry_text}".lower()

    icp_hit = _find_in_icp(company_name, icp_data)
    if icp_hit:
        industry, category, matched_name = icp_hit
        for substr, customer_type in _ICP_CATEGORY_TO_CUSTOMER_TYPE:
            if substr in category.lower():
                return {
                    "customer_type": customer_type,
                    "confidence": "icp_match",
                    "matched_via": f"ICP list: '{matched_name}' under {industry} / {category}",
                    "candidates": [customer_type],
                }
        haystack = f"{haystack} {industry}".lower()

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
