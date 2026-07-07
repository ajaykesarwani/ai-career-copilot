"""
External Tool — Adzuna Job Search API

This is a formal "tool" in the agentic sense (5-Day AI Agents course
terminology): a typed, well-documented function the JobRanker agent calls
to fetch grounded, real-world data instead of asking the LLM to invent it.

Adzuna (https://developer.adzuna.com) was chosen because:
  - Free tier: 250 calls/month/app — no payment details required to sign up
  - Real, live job postings (not hallucinated)
  - Supports `where=` location filtering and `max_days_old=` recency filtering
    natively — exactly the two requirements (strict location + freshness)
  - Covers 20+ countries, mapped below

Get free credentials at: https://developer.adzuna.com/

If ADZUNA_APP_ID / ADZUNA_APP_KEY are not set, callers should treat this
tool as unavailable and fall back to the AI-estimate path — handled by the
caller (job_ranker.py), not here.
"""

from __future__ import annotations
import os
import re
import logging
import httpx
from datetime import datetime, timezone

logger = logging.getLogger("adzuna_tool")
ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"

# Adzuna's country-code endpoints. Used to route a free-text location to the
# right regional index. Defaults to "us" (largest index) when no match.
_COUNTRY_HINTS = {
    "us": ["usa", "united states", "us", "america", "new york", "san francisco",
           "seattle", "austin", "boston", "chicago", "remote us"],
    "gb": ["uk", "united kingdom", "england", "london", "manchester", "scotland",
           "edinburgh", "bristol", "leeds"],
    "de": ["germany", "berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne", "köln"],
    "fr": ["france", "paris", "lyon", "marseille", "toulouse"],
    "ca": ["canada", "toronto", "vancouver", "montreal", "ottawa"],
    "au": ["australia", "sydney", "melbourne", "brisbane", "perth"],
    "in": ["india", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad", "pune"],
    "nl": ["netherlands", "amsterdam", "rotterdam", "the hague"],
    "es": ["spain", "madrid", "barcelona", "valencia"],
    "it": ["italy", "milan", "rome", "milano"],
    "pl": ["poland", "warsaw", "warszawa", "krakow", "kraków"],
    "sg": ["singapore"],
    "nz": ["new zealand", "auckland", "wellington"],
    "ie": ["ireland", "dublin"],
    "za": ["south africa", "johannesburg", "cape town"],
    "br": ["brazil", "são paulo", "sao paulo", "rio de janeiro"],
    "mx": ["mexico", "mexico city"],
}


def _detect_country(location_text: str) -> str:
    loc = (location_text or "").lower()
    for code, hints in _COUNTRY_HINTS.items():
        if any(h in loc for h in hints):
            return code
    return "us"


def _extract_city(location_text: str, country_code: str) -> str:
    """Best-effort extraction of just the city/area portion for the `where=` param."""
    loc = (location_text or "").strip()
    if not loc:
        return ""
    # Strip the country name itself if present so we pass just the city to Adzuna
    lowered = loc.lower()
    for hints in _COUNTRY_HINTS.values():
        for h in hints:
            if lowered == h:
                return ""  # whole string was just the country — no city filter
    # Take first comma-separated segment as the city (e.g. "Berlin, Germany" -> "Berlin")
    first_part = re.split(r"[,/]", loc)[0].strip()
    return first_part


def is_configured() -> bool:
    return bool(os.getenv("ADZUNA_APP_ID") and os.getenv("ADZUNA_APP_KEY"))


async def search_jobs(
    *,
    query: str,
    location_text: str = "",
    max_days_old: int = 21,
    remote_only: bool = False,
    results: int = 15,
) -> list[dict]:
    """
    Query the Adzuna API for real, recent job postings.

    Returns a list of normalised job dicts (already shaped close to our
    `Job` schema) or an empty list if the API is unavailable / unconfigured.
    Never raises — callers should treat an empty list as "no live data,
    fall back to AI estimate".
    """
    app_id = os.getenv("ADZUNA_APP_ID", "").strip()
    app_key = os.getenv("ADZUNA_APP_KEY", "").strip()
    if not app_id or not app_key:
        logger.warning("ADZUNA_APP_ID or ADZUNA_APP_KEY not set — skipping live search")
        return []

    country = _detect_country(location_text)
    city = _extract_city(location_text, country)

    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": query,
        "results_per_page": min(results, 50),
        "max_days_old": max(1, min(max_days_old, 60)),
        "sort_by": "date",
        "content-type": "application/json",
    }
    if city:
        params["where"] = city
    if remote_only:
        params["what"] = f"{query} remote"

    url = f"{ADZUNA_BASE}/{country}/search/1"
    logger.info("Adzuna request: url=%s query=%r city=%r country=%s max_days=%d",
                url, query, city, country, max_days_old)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            logger.info("Adzuna response: status=%d", resp.status_code)
            if resp.status_code == 401:
                logger.error("Adzuna 401 Unauthorized — check ADZUNA_APP_ID and ADZUNA_APP_KEY values")
                return []
            if resp.status_code == 400:
                logger.error("Adzuna 400 Bad Request — response: %s", resp.text[:300])
                return []
            if resp.status_code != 200:
                logger.error("Adzuna non-200: %d — %s", resp.status_code, resp.text[:200])
                return []
            data = resp.json()
            count = data.get("count", 0)
            results_list = data.get("results", [])
            logger.info("Adzuna success: count=%d results_returned=%d", count, len(results_list))
    except httpx.TimeoutException:
        logger.error("Adzuna request timed out after 15s")
        return []
    except Exception as e:
        logger.error("Adzuna request exception: %s", e)
        return []

    jobs = []
    for r in data.get("results", []):
        jobs.append(_normalise(r))
    return jobs


def _clean_html(text: str) -> str:
    if not text:
        return ""
    # Strip HTML tags
    text = re.sub(r"<[^>]*>", "", text)
    import html
    return html.unescape(text)


def _normalise(raw: dict) -> dict:
    """Map an Adzuna result object into our internal job shape."""
    created = raw.get("created", "")
    posted_label, iso = _format_recency(created)

    loc = raw.get("location", {}).get("display_name", "Remote")
    title = _clean_html(raw.get("title", ""))
    desc = _clean_html(raw.get("description", ""))

    title_l = title.lower()
    desc_l = desc.lower()
    is_remote = "remote" in loc.lower() or "remote" in title_l or "work from home" in desc_l

    salary_min = raw.get("salary_min")
    salary_max = raw.get("salary_max")
    if salary_min and salary_max:
        salary = f"£{int(salary_min):,} – £{int(salary_max):,}" if raw.get("salary_is_predicted") == "0" \
            else f"~£{int(salary_min):,} – £{int(salary_max):,} (estimated)"
    else:
        salary = "Not disclosed"

    category = raw.get("category", {}).get("label", "")
    tags = [t for t in [category] if t][:3]

    return {
        "title": title.strip() or "Untitled role",
        "company": (raw.get("company", {}) or {}).get("display_name", "Unknown company"),
        "location": loc,
        "type": "remote" if is_remote else "onsite",
        "salary": salary,
        "tags": tags or ["General"],
        "logo": "💼",
        "desc": _clean_description(desc),
        "posted": posted_label,
        "date_posted_iso": iso,
        "url": raw.get("redirect_url", "#"),
        "source": "adzuna",
    }



def _clean_description(desc: str, max_len: int = 220) -> str:
    desc = re.sub(r"\s+", " ", desc or "").strip()
    if len(desc) > max_len:
        desc = desc[:max_len].rsplit(" ", 1)[0] + "…"
    return desc


def _format_recency(created_iso: str) -> tuple[str, str]:
    """Convert Adzuna's created timestamp into a human label + clean ISO date."""
    if not created_iso:
        return "Recently", ""
    try:
        dt = datetime.fromisoformat(created_iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta_days = (now - dt).days
        if delta_days <= 0:
            label = "Today"
        elif delta_days == 1:
            label = "1d ago"
        else:
            label = f"{delta_days}d ago"
        return label, dt.date().isoformat()
    except Exception:
        return "Recently", ""
