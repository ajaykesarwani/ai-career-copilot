"""
Agent 7 — LinkedIn Enrichment
==============================
Three-tier approach to extracting LinkedIn profile data:

Tier 1 (API scraper) — uses `linkedin-api` (unofficial Python library that
  authenticates with LinkedIn cookies/credentials and reads the API LinkedIn
  itself uses for its mobile app). Requires LINKEDIN_EMAIL + LINKEDIN_PASSWORD
  in .env. Works reliably if credentials are valid; LinkedIn may rate-limit
  aggressive use. This is an unofficial library — use responsibly.

Tier 2 (public profile HTML) — fetches the public-facing profile page with a
  browser User-Agent. Extracts visible text. Less structured than the API, but
  works without credentials for public profiles.

Tier 3 (paste-text) — the user copies their LinkedIn About / experience text
  and pastes it directly. Gemini then structures it into experience entries,
  skills, and a summary. This fallback always works.

All three tiers feed the same Gemini structuring step, which normalises the
raw input into a clean dict regardless of which tier provided the data.
"""

from __future__ import annotations
import os
import re
import json
from .base import BaseAgent
from utils.observability import traced
from utils.guardrails import sanitize_for_prompt


class LinkedInAgent(BaseAgent):
    name = "LinkedInAgent"
    system = (
        "You are an expert at extracting and structuring professional profile data "
        "from LinkedIn. Extract information accurately and completely. "
        "Return only valid JSON."
    )

    @traced("LinkedInAgent", "enrich")
    async def enrich(self, linkedin_url: str = "", linkedin_text: str = "") -> dict:
        """
        Enrich profile with LinkedIn data. Tries each tier in order and uses
        the first that returns usable data.
        """
        raw_data = ""
        source = "none"

        # ── Tier 1: linkedin-api scraper ─────────────────────────────────────
        if linkedin_url and self._api_configured():
            try:
                raw_data = await self._scrape_via_api(linkedin_url)
                source = "api"
            except Exception:
                pass

        # ── Tier 2: public profile HTML fetch ────────────────────────────────
        if not raw_data and linkedin_url:
            try:
                raw_data = await self._fetch_public_profile(linkedin_url)
                source = "public_html"
            except Exception:
                pass

        # ── Tier 3: pasted text ───────────────────────────────────────────────
        if not raw_data and linkedin_text:
            raw_data = linkedin_text
            source = "pasted_text"

        if not raw_data:
            return {"linkedin_structured": {}, "linkedin_source": "none"}

        # All tiers feed the same structuring step
        structured = await self._structure_with_llm(raw_data, source)
        structured["linkedin_source"] = source
        return structured

    # ── Tier 1: linkedin-api ─────────────────────────────────────────────────

    def _api_configured(self) -> bool:
        return bool(os.getenv("LINKEDIN_EMAIL") and os.getenv("LINKEDIN_PASSWORD"))

    async def _scrape_via_api(self, profile_url: str) -> str:
        """Use linkedin-api to fetch structured profile data."""
        import asyncio
        from linkedin_api import Linkedin

        email    = os.getenv("LINKEDIN_EMAIL", "")
        password = os.getenv("LINKEDIN_PASSWORD", "")

        # Extract the username/vanity-URL slug from the profile URL
        slug = profile_url.rstrip("/").split("/in/")[-1].split("/")[0].split("?")[0]
        if not slug:
            return ""

        def _fetch():
            try:
                api     = Linkedin(email, password, authenticate=True)
                profile = api.get_profile(slug)
                skills  = api.get_profile_skills(slug)
                return profile, skills
            except Exception as e:
                raise RuntimeError(f"linkedin-api: {e}")

        loop = asyncio.get_event_loop()
        profile, skills = await loop.run_in_executor(None, _fetch)

        if not profile:
            return ""

        # Flatten into a readable text block the LLM can structure
        parts = []
        if profile.get("firstName") or profile.get("lastName"):
            parts.append(f"Name: {profile.get('firstName','')} {profile.get('lastName','')}")
        if profile.get("headline"):
            parts.append(f"Headline: {profile['headline']}")
        if profile.get("summary"):
            parts.append(f"About: {profile['summary'][:1000]}")
        if profile.get("locationName"):
            parts.append(f"Location: {profile['locationName']}")

        # Experience
        for exp in (profile.get("experience") or [])[:6]:
            company = (exp.get("companyName") or "")
            title   = (exp.get("title") or "")
            dates   = f"{exp.get('timePeriod', {}).get('startDate', {}).get('year','?')} – " \
                      f"{exp.get('timePeriod', {}).get('endDate', {}).get('year', 'Present')}"
            desc    = (exp.get("description") or "")[:300]
            parts.append(f"Experience: {title} at {company} ({dates}). {desc}")

        # Education
        for edu in (profile.get("education") or [])[:3]:
            school  = edu.get("schoolName", "")
            degree  = edu.get("degreeName", "")
            field   = edu.get("fieldOfStudy", "")
            parts.append(f"Education: {degree} {field} — {school}")

        # Skills from dedicated endpoint
        if skills:
            skill_names = [s.get("name", "") for s in skills[:20] if s.get("name")]
            parts.append(f"Skills: {', '.join(skill_names)}")

        return "\n".join(parts)

    # ── Tier 2: public HTML fetch ─────────────────────────────────────────────

    async def _fetch_public_profile(self, profile_url: str) -> str:
        """Fetch the public LinkedIn profile page and extract visible text."""
        import httpx
        import asyncio

        # Ensure it's the www.linkedin.com/in/... form
        if "linkedin.com/in/" not in profile_url:
            return ""

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        async with httpx.AsyncClient(
            timeout=15, follow_redirects=True,
            headers=headers,
        ) as client:
            r = await client.get(profile_url)
            if r.status_code != 200:
                return ""
            html = r.text

        # Strip script/style tags then extract text
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>",  "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()

        # LinkedIn public pages are heavily JS-rendered — we get meta content
        # but the text we extract is still useful for names, titles, and visible summary.
        # Cap at 4000 chars to avoid token overflow
        return text[:4000] if len(text) > 100 else ""

    # ── LLM structuring (all tiers feed here) ─────────────────────────────────

    async def _structure_with_llm(self, raw_text: str, source: str) -> dict:
        """Use Gemini to extract structured fields from raw LinkedIn text."""
        safe = sanitize_for_prompt(raw_text, max_len=5000)

        prompt = f"""Extract structured professional profile data from this LinkedIn content.
Source type: {source}

CONTENT:
\"\"\"
{safe}
\"\"\"

Return ONLY a valid JSON object with these keys:
{{
  "name": "Full Name or empty string",
  "headline": "Professional headline",
  "location": "City, Country or empty",
  "summary": "About section, 2-4 sentences",
  "experience": [
    {{"title": "Job Title", "company": "Company", "duration": "2020-2023", "description": "Key responsibilities..."}}
  ],
  "education": [
    {{"degree": "BSc Computer Science", "school": "University Name", "year": "2018"}}
  ],
  "skills": ["skill1", "skill2"],
  "certifications": ["cert1"],
  "years_exp": 5
}}

If a field cannot be found in the content, use empty string or empty array.
Return ONLY the JSON object, no markdown, no extra text."""

        data = await self.call_json([{"role": "user", "content": prompt}], max_tokens=1000)

        # Map to profile update fields
        return {
            "linkedin_structured": data,
            # Promote key fields to top-level profile if not already set
            "linkedin_name":     data.get("name", ""),
            "linkedin_headline": data.get("headline", ""),
            "linkedin_location": data.get("location", ""),
            "linkedin_summary":  data.get("summary", ""),
            "linkedin_skills":   data.get("skills", []),
            "linkedin_years_exp": int(data.get("years_exp", 0) or 0),
            "linkedin_education": "; ".join(
                f"{e.get('degree','')} — {e.get('school','')}"
                for e in data.get("education", [])[:2]
            ),
        }
