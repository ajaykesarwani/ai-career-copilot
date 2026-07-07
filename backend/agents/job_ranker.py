"""
Agent 4 — Job Discovery & Ranker

Tool-using agent (5-Day AI Agents course pattern): this agent's primary
path calls a real external tool (Adzuna job search API) to fetch grounded,
live job postings, then uses Gemini purely for *ranking/scoring* against
the candidate profile — not for inventing postings.

Location handling:
  - location_mode == "strict": ONLY returns jobs at/near the requested
    location (plus remote roles if the user opted into remote). No
    worldwide fallback in strict mode — honours the user's explicit intent.
  - location_mode == "any" (default): searches the requested location first;
    if too few results, broadens to a worldwide search so the user still
    gets a useful list.

Recency: Adzuna's `max_days_old` + `sort_by=date` are used directly, so
results are inherently fresh. We additionally re-filter and re-sort by
`date_posted_iso` after fetch, and drop anything older than the requested
window as a safety net against stale cached results.

If Adzuna is not configured (no ADZUNA_APP_ID/KEY) or returns nothing,
this agent transparently falls back to an LLM-estimated list — each such
job is explicitly tagged source="ai_estimate" so the frontend can show a
"Estimated — verify on company site" badge and never confuse it with a
real, verified listing.
"""

import uuid
import logging
from datetime import datetime, timezone
from .base import BaseAgent
from utils.observability import traced
from utils.guardrails import sanitize_for_prompt
from utils import job_search_tool

logger = logging.getLogger("job_ranker")



class JobRankerAgent(BaseAgent):
    name = "JobRanker"
    system = (
        "You are a recruitment intelligence system. You score and explain how well "
        "real job postings match a candidate profile. Return only valid JSON."
    )

    @traced("JobRanker", "discover_and_rank")
    async def discover_and_rank(self, profile: dict, preferences: dict) -> list[dict]:
        """Return list of ranked job dicts, real data preferred over AI estimates."""

        location_text = (preferences.get("locations") or "").strip()
        location_mode = preferences.get("location_mode", "any")
        max_days_old = int(preferences.get("max_days_old", 21) or 21)
        remote_ok = bool(preferences.get("remote", True))

        query = self._build_query(profile, preferences)

        real_jobs: list[dict] = []
        if job_search_tool.is_configured():
            real_jobs = await job_search_tool.search_jobs(
                query=query,
                location_text=location_text,
                max_days_old=max_days_old,
                remote_only=False,
                results=20,
            )

            # Strict mode: keep ONLY postings that actually match the requested
            # location (or are remote, if the user allows remote).
            if location_text and location_mode == "strict":
                real_jobs = [
                    j for j in real_jobs
                    if self._location_matches(j["location"], location_text)
                    or (remote_ok and j["type"] == "remote")
                ]
            elif location_text and len(real_jobs) < 4:
                # "any" mode: if the targeted search came back thin, broaden to
                # a worldwide search so the user still gets useful results.
                broader = await job_search_tool.search_jobs(
                    query=query, location_text="", max_days_old=max_days_old, results=20,
                )
                seen = {(j["company"], j["title"]) for j in real_jobs}
                for j in broader:
                    if (j["company"], j["title"]) not in seen:
                        real_jobs.append(j)

            # Recency safety net — drop anything outside the freshness window
            real_jobs = [j for j in real_jobs if self._within_recency(j.get("date_posted_iso"), max_days_old)]

        if real_jobs:
            ranked = await self._score_real_jobs(real_jobs[:16], profile, preferences)
        else:
            # No live data available — transparent AI-estimate fallback.
            ranked = await self._estimate_jobs(profile, preferences, location_text, location_mode)

        result = []
        for j in ranked:
            j["id"] = f"j_{uuid.uuid4().hex[:8]}"
            j.setdefault("selected", False)
            j.setdefault("url", "#")
            j.setdefault("source", "ai_estimate")
            result.append(j)

        # Final sort: best match first, recency as tiebreaker
        result.sort(key=lambda j: (-j.get("match", 0), j.get("date_posted_iso", "") or ""), reverse=False)
        result.sort(key=lambda j: -j.get("match", 0))
        return result[:12]

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _build_query(self, profile: dict, preferences: dict) -> str:
        roles = preferences.get("roles") or profile.get("title") or "Software Engineer"
        # Use only the first target role for the primary search query — Adzuna's
        # `what` param works best as a focused phrase, not a long OR list.
        first_role = roles.split(",")[0].strip()
        return first_role or "Software Engineer"

    def _location_matches(self, job_location: str, requested: str) -> bool:
        job_loc = (job_location or "").lower()
        req_parts = [p.strip().lower() for p in requested.split(",") if p.strip()]
        return any(part in job_loc or job_loc in part for part in req_parts if part)

    def _within_recency(self, iso_date: str | None, max_days_old: int) -> bool:
        if not iso_date:
            return True  # unknown date — don't penalise, recency already enforced by API call
        try:
            posted = datetime.fromisoformat(iso_date).replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - posted).days
            return age_days <= max_days_old + 1  # +1 day buffer for timezone edges
        except Exception:
            return True

    @traced("JobRanker", "score_real_jobs")
    async def _score_real_jobs(self, jobs: list[dict], profile: dict, preferences: dict) -> list[dict]:
        """Ask Gemini to score real postings against the candidate — grounded scoring, not invention."""

        job_summaries = "\n".join(
            f"{i+1}. {j['title']} at {j['company']} ({j['location']}) — {sanitize_for_prompt(j['desc'], 300)}"
            for i, j in enumerate(jobs)
        )

        prompt = f"""Score how well each job posting matches this candidate (0-100) and pick the 3 most relevant skill tags per job.

CANDIDATE:
Title: {profile.get('title', 'Software Engineer')}
Skills: {', '.join(profile.get('skills', [])[:12])}
Years experience: {profile.get('years_exp', 3)}
Target seniority: {preferences.get('seniority', 'Mid-level')}

JOB POSTINGS:
{job_summaries}

Return ONLY a JSON array, one object per job, in the SAME ORDER as listed above:
[{{"match": 78, "tags": ["skill1","skill2","skill3"], "logo": "single relevant emoji"}}]

Match scores must be honest — only give 85+ for a strong, genuine skill alignment."""

        try:
            scores = await self.call_json([{"role": "user", "content": prompt}], max_tokens=1500)
            if not isinstance(scores, list) or len(scores) != len(jobs):
                scores = [{"match": 70, "tags": j.get("tags", ["General"])[:3], "logo": "💼"} for j in jobs]
        except Exception as e:
            logger.warning("Gemini job scoring failed, falling back to heuristic: %s", e)
            scores = [{"match": 70, "tags": j.get("tags", ["General"])[:3], "logo": "💼"} for j in jobs]


        merged = []
        for job, score in zip(jobs, scores):
            merged.append({
                **job,
                "match": int(score.get("match", 70)),
                "tags": score.get("tags") or job.get("tags", ["General"]),
                "logo": score.get("logo") or "💼",
            })
        return merged

    @traced("JobRanker", "estimate_jobs_fallback")
    async def _estimate_jobs(self, profile: dict, preferences: dict, location_text: str, location_mode: str) -> list[dict]:
        """
        Fallback path when no real job API is configured/available.
        Every job returned here is explicitly tagged source="ai_estimate".
        """
        location_clause = (
            f"ONLY in or near: {location_text} (plus remote roles if remote work is acceptable). "
            f"Do not include jobs from other locations."
            if location_text and location_mode == "strict"
            else f"Prefer locations near: {location_text}. If insufficient, include relevant global/remote roles."
            if location_text
            else "Include a global mix of locations, prioritising remote-friendly roles."
        )

        prompt = f"""Generate 8 realistic, plausible job postings for this candidate.
These are ESTIMATES (no live job board available) — be clear they should resemble
typical current postings at real, well-known companies in this space, but do not
claim they are live/verified.

CANDIDATE:
Title: {profile.get('title', 'Software Engineer')}
Skills: {', '.join(profile.get('skills', [])[:12])}
Years experience: {profile.get('years_exp', 3)}

PREFERENCES:
Target roles: {preferences.get('roles', '')}
Location requirement: {location_clause}
Salary: {preferences.get('salary', '')}
Seniority: {preferences.get('seniority', 'Mid-level')}
Industries: {preferences.get('industries', '')}

Return a JSON array of 8 job objects:
{{
  "title": "Job Title", "company": "Real Company Name", "location": "City / Remote",
  "type": "remote|hybrid|onsite", "salary": "currency range", "match": 78,
  "tags": ["skill1","skill2","skill3"], "logo": "emoji", "desc": "2-sentence description",
  "posted": "Recently"
}}

Match scores (60-98) must reflect honest skill alignment. Sort by match descending.
Return ONLY the JSON array."""

        data = await self.call_json([{"role": "user", "content": prompt}], max_tokens=2000)
        jobs = data if isinstance(data, list) else data.get("jobs", [])

        for j in jobs:
            j["source"] = "ai_estimate"
            j.setdefault("posted", "Recently")
            j.setdefault("date_posted_iso", "")
        return jobs
