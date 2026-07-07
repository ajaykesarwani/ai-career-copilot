"""
Jobs router — Adzuna-first job search with Gemini scoring.

FIXED architecture (v5→v6):
  Previous versions ran LangChain/ADK LLM agents FIRST, which asked Gemini
  to generate or find jobs — Adzuna was only called IF the LLM decided to
  invoke its tool, which it often skipped in favour of generating content itself.

  New architecture (this file):
    Step 1: Call Adzuna API DIRECTLY (no LLM in the loop)
    Step 2: Score the real results with Gemini
    Step 3: If Adzuna returns nothing / isn't configured → AI estimate fallback

  This guarantees: if ADZUNA_APP_ID + ADZUNA_APP_KEY are set, real jobs appear.
"""

import sys, os, uuid, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import APIRouter
from models.schemas import JobSearchRequest, JobSearchResponse, Job
from agents import JobRankerAgent
from utils import job_search_tool
from utils.observability import record_trace
import time

logger = logging.getLogger("jobs_router")
router  = APIRouter()
_ranker = JobRankerAgent()


def _normalise(j: dict) -> dict:
    j.setdefault("id",              f"j_{uuid.uuid4().hex[:8]}")
    j.setdefault("selected",        False)
    j.setdefault("source",          "ai_estimate")
    j.setdefault("logo",            "💼")
    j.setdefault("tags",            [])
    j.setdefault("date_posted_iso", "")
    j.setdefault("url",             "#")
    j.setdefault("salary",          "Not disclosed")
    j.setdefault("posted",          "Recently")
    j["match"] = int(j.get("match", 70))
    return j


@router.post("/search", response_model=JobSearchResponse)
async def search_jobs(req: JobSearchRequest):
    profile = req.profile.model_dump()
    prefs   = req.profile.preferences.model_dump()

    location_text = (prefs.get("locations") or "").strip()
    location_mode = prefs.get("location_mode", "any")
    max_days_old  = int(prefs.get("max_days_old", 21) or 21)
    query = (prefs.get("roles") or profile.get("title") or "Software Engineer").split(",")[0].strip()

    jobs: list[dict] = []
    using_live = False
    t = time.monotonic()

    # ── Step 1: Direct Adzuna call (no LLM in the way) ───────────────────────
    if job_search_tool.is_configured():
        logger.info("Adzuna configured — fetching live jobs: query=%r location=%r", query, location_text)
        try:
            raw_jobs = await job_search_tool.search_jobs(
                query=query,
                location_text=location_text,
                max_days_old=max_days_old,
                results=20,
            )

            # Location enforcement
            if raw_jobs and location_text and location_mode == "strict":
                filtered = [
                    j for j in raw_jobs
                    if _location_matches(j.get("location", ""), location_text)
                    or j.get("type") == "remote"
                ]
                # If strict filtering leaves nothing, keep all (better UX than empty)
                raw_jobs = filtered if filtered else raw_jobs

            # If location-specific search returned too few, broaden to worldwide
            if len(raw_jobs) < 4 and location_text and location_mode != "strict":
                logger.info("Too few local results (%d) — broadening to worldwide", len(raw_jobs))
                broader = await job_search_tool.search_jobs(
                    query=query, location_text="", max_days_old=max_days_old, results=15,
                )
                seen = {(j["company"], j["title"]) for j in raw_jobs}
                for j in broader:
                    if (j["company"], j["title"]) not in seen:
                        raw_jobs.append(j)

            if raw_jobs:
                logger.info("Adzuna returned %d live jobs — scoring with Gemini", len(raw_jobs))
                # Step 2: Score real jobs with Gemini (match %, tags, logo)
                jobs = await _ranker._score_real_jobs(raw_jobs[:16], profile, prefs)
                using_live = True
                record_trace("JobsRouter", "adzuna_live", int((time.monotonic()-t)*1000), True,
                             {"count": len(jobs), "query": query, "location": location_text})
            else:
                logger.warning("Adzuna returned 0 results for query=%r location=%r", query, location_text)

        except Exception as e:
            logger.error("Adzuna call failed: %s", e)
            record_trace("JobsRouter", "adzuna_error", int((time.monotonic()-t)*1000), False, {"error": str(e)})

    # ── Step 3: AI-estimate fallback (Adzuna not configured or returned nothing) ──
    if not jobs:
        logger.info("Falling back to AI-estimated jobs (Adzuna configured=%s)", job_search_tool.is_configured())
        try:
            jobs = await _ranker._estimate_jobs(profile, prefs, location_text, location_mode)
            record_trace("JobsRouter", "ai_estimate_fallback", int((time.monotonic()-t)*1000), True,
                         {"count": len(jobs)})
        except Exception as e:
            logger.error("AI estimate also failed: %s", e)
            jobs = []

    # Client-side filters
    if req.filter_type:
        jobs = [j for j in jobs if j.get("type") == req.filter_type]
    if req.filter_match == "high":
        jobs = [j for j in jobs if j.get("match", 0) >= 85]
    elif req.filter_match == "med":
        jobs = [j for j in jobs if j.get("match", 0) >= 65]

    normalised = [_normalise(j) for j in jobs]
    logger.info("Returning %d jobs (live=%s)", len(normalised), using_live)
    return JobSearchResponse(jobs=[Job(**j) for j in normalised], total=len(normalised))


@router.get("/source-status")
async def source_status():
    configured = job_search_tool.is_configured()
    # Also verify env vars are actually readable (not just set to empty string)
    app_id  = os.getenv("ADZUNA_APP_ID", "")
    app_key = os.getenv("ADZUNA_APP_KEY", "")
    return {
        "live_job_search_configured": configured,
        "provider": "Adzuna" if configured else None,
        "adzuna_app_id_set":  bool(app_id  and app_id  != "your-adzuna-app-id"),
        "adzuna_app_key_set": bool(app_key and app_key != "your-adzuna-app-key"),
        "note": (
            "Live job search active — real Adzuna postings will be returned."
            if configured else
            "No Adzuna keys found. Jobs will be AI-estimated. "
            "Add ADZUNA_APP_ID and ADZUNA_APP_KEY to .env for live listings."
        ),
    }


def _location_matches(job_location: str, requested: str) -> bool:
    job = (job_location or "").lower()
    for part in requested.split(","):
        p = part.strip().lower()
        if p and (p in job or job in p):
            return True
    return False
