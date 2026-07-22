"""Optional cost-control pre-trim before the LLM. OFF by default
(never_send_titles: [] in settings) — pure spend control, never judgment.
When enabled, matching employees are auto-skipped with a 'prefiltered' note
instead of being sent to the judge."""

from __future__ import annotations


def should_prefilter(title: str | None, never_send_titles: list[str]) -> bool:
    if not title or not never_send_titles:
        return False
    title_lower = title.lower()
    return any(term.lower() in title_lower for term in never_send_titles)
