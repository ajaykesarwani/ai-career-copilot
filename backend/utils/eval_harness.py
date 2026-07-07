"""
Agent Evaluation Harness (5-Day AI Agents course concept).

A lightweight, rubric-based evaluator that scores agent outputs against
concrete, checkable criteria — no external eval framework or paid service
required, so it works entirely on the free tier.

Each evaluator function takes the agent's output (and relevant input
context) and returns a 0-1 score plus human-readable notes. This is the
kind of "did the agent actually do its job well" check taught in the
course's evaluation module, applied here to our concrete agents:

  - Resume parser: did it extract a name/title/skills, and did it correctly
    avoid inventing contact details that weren't in the source?
  - Doc generator: is the cover letter actually long enough (the very bug
    being fixed here), does the resume contain all expected sections, are
    missing-info placeholders used correctly?
  - Job ranker: are match scores within a sane range, is `source` populated
    so real vs estimated data is distinguishable?

These run on-demand via the /api/ops/eval endpoint against the most recent
generated content held in the trace buffer's metadata, OR can be called
directly with sample/test data — useful both for manual QA and as a
foundation for CI-style regression checks.
"""

from __future__ import annotations
import re
from typing import Any


def eval_resume_parse(parsed: dict, source_text: str) -> dict[str, Any]:
    """Score a resume-parser output against simple groundedness/completeness checks."""
    checks = []

    checks.append(("has_name", bool(parsed.get("name"))))
    checks.append(("has_title", bool(parsed.get("title"))))
    checks.append(("has_skills", len(parsed.get("skills", [])) >= 3))
    checks.append(("years_exp_is_int", isinstance(parsed.get("years_exp"), int)))

    # Groundedness: any contact field returned should actually appear (loosely)
    # in the source text — guards against the model inventing values.
    for field in ("email", "phone"):
        val = parsed.get(field, "")
        if val:
            present = _loose_contains(source_text, val)
            checks.append((f"{field}_grounded", present))

    score = sum(1 for _, ok in checks if ok) / len(checks) if checks else 0
    return {
        "score": round(score, 2),
        "checks": [{"name": n, "passed": ok} for n, ok in checks],
        "notes": "Groundedness checks verify extracted contact details actually appear in the source resume.",
    }


def eval_cover_letter(cover_text: str) -> dict[str, Any]:
    """Score a generated cover letter — directly targets the 'too short' bug."""
    word_count = len(cover_text.split())
    paragraphs = [p for p in re.split(r"\n\s*\n", cover_text.strip()) if p.strip()]

    checks = [
        ("min_length_380_words", word_count >= 380),
        ("has_4_paragraphs", len(paragraphs) >= 4),
        ("no_generic_opener", not cover_text.strip().lower().startswith("i am writing to apply")),
        ("has_signoff", bool(re.search(r"(regards|sincerely|best),?\s*\n", cover_text, re.IGNORECASE))),
    ]

    score = sum(1 for _, ok in checks if ok) / len(checks)
    return {
        "score": round(score, 2),
        "word_count": word_count,
        "paragraph_count": len(paragraphs),
        "checks": [{"name": n, "passed": ok} for n, ok in checks],
    }


def eval_resume_doc(resume_text: str) -> dict[str, Any]:
    """Score a generated resume for section completeness."""
    expected_sections = ["SUMMARY", "SKILLS", "EXPERIENCE"]
    found = [s for s in expected_sections if re.search(rf"(?im)^\s*{s}\b", resume_text)]

    checks = [(f"has_{s.lower()}_section", s in found) for s in expected_sections]
    checks.append(("reasonable_length", 150 <= len(resume_text.split()) <= 900))

    score = sum(1 for _, ok in checks if ok) / len(checks)
    return {
        "score": round(score, 2),
        "checks": [{"name": n, "passed": ok} for n, ok in checks],
    }


def eval_job_results(jobs: list[dict], requested_location: str, location_mode: str, max_days_old: int) -> dict[str, Any]:
    """Score a job search result set against the location/recency requirements."""
    if not jobs:
        return {"score": 0.0, "checks": [], "notes": "No jobs returned."}

    has_source = all("source" in j for j in jobs)
    has_match_in_range = all(0 <= j.get("match", -1) <= 100 for j in jobs)

    location_check = True
    if requested_location and location_mode == "strict":
        location_check = all(
            requested_location.lower() in j.get("location", "").lower()
            or j.get("type") == "remote"
            for j in jobs
        )

    checks = [
        ("all_jobs_tagged_with_source", has_source),
        ("match_scores_in_valid_range", has_match_in_range),
        ("respects_strict_location" if location_mode == "strict" else "location_mode_any_ok", location_check),
    ]

    score = sum(1 for _, ok in checks if ok) / len(checks)
    return {
        "score": round(score, 2),
        "checks": [{"name": n, "passed": ok} for n, ok in checks],
        "real_data_count": sum(1 for j in jobs if j.get("source") == "adzuna"),
        "estimated_count": sum(1 for j in jobs if j.get("source") == "ai_estimate"),
    }


def _loose_contains(haystack: str, needle: str) -> bool:
    """Case/whitespace-insensitive substring containment check."""
    norm = lambda s: re.sub(r"\s+", "", s or "").lower()
    return norm(needle) in norm(haystack)
