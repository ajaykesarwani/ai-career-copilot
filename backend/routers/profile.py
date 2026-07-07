"""
Profile router — resume upload + layout analysis + LinkedIn + GitHub + analysis.

On upload:
  1. Extract text (PyPDF2 → Gemini Vision OCR fallback for scanned PDFs)
  2. Run layout analysis in parallel (Gemini Vision reads visual design)
  3. Parse structured profile fields with ADK / original agent
  4. Return profile with extraction_method + resume_layout for UI transparency

Socials enrichment:
  - GitHub: REST (repos, languages, contributions) + GraphQL (pinned repos)
    + profile README fetch
  - LinkedIn: 3-tier (linkedin-api scraper → public HTML → paste-text),
    all normalised through Gemini LLM structuring
"""

import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import APIRouter, UploadFile, File, HTTPException
from models.schemas import (
    CandidateProfile, SocialsRequest, AnalysisRequest,
    AnalysisResponse, ResumeLayout,
)
from agents import (
    ResumeParserAgent, GitHubAgent, LinkedInAgent, ProfileMergerAgent,
    get_adk_resume_parser, get_adk_profile_merger,
    run_profile_pipeline,
)
from utils import extract_text, layout_analyser
from utils.guardrails import screen_text

router = APIRouter()

_resume_parser = ResumeParserAgent()
_github_agent  = GitHubAgent()
_linkedin_agent = LinkedInAgent()
_merger_agent  = ProfileMergerAgent()


@router.post("/parse", response_model=CandidateProfile)
async def parse_resume(file: UploadFile = File(...)):
    """
    Upload resume → extract text + detect visual layout in parallel.
    Scanned PDFs are automatically OCR'd via Gemini Vision.
    Layout analysis (columns, accent colour, section order) runs simultaneously
    so the generated documents can reproduce the user's own style.
    """
    max_mb = int(os.getenv("MAX_UPLOAD_MB", 10))
    content = await file.read()
    if len(content) > max_mb * 1024 * 1024:
        raise HTTPException(413, f"File too large — max {max_mb}MB")

    fname = file.filename or "resume.pdf"

    # Run text extraction and layout analysis in parallel
    extraction_task = asyncio.to_thread(extract_text, content, fname)
    layout_task     = layout_analyser.analyse_layout(content, fname)
    extraction, layout_raw = await asyncio.gather(extraction_task, layout_task)

    raw_text = extraction["text"]
    method   = extraction["method"]

    if not raw_text.strip():
        raise HTTPException(
            422,
            "Could not extract text from this file even after OCR. "
            "Try a text-based PDF, a DOCX, or paste as .txt."
        )

    guard = screen_text(raw_text, source="resume_upload")
    if not guard.safe:
        raw_text = "[Content flagged as potentially unsafe and excluded from parsing.]"

    # Parse structured fields — ADK primary, original fallback
    parsed = {}
    try:
        adk_parser = get_adk_resume_parser()
        parsed = await adk_parser.parse(raw_text)
    except Exception:
        try:
            parsed = await _resume_parser.parse(raw_text)
        except Exception as e:
            raise HTTPException(500, f"Resume parsing failed: {e}")

    # --- NORMALIZE ADK OUTPUT TO MATCH CandidateProfile SCHEMA ---

    # top_projects: list[str]
    projects = parsed.get("top_projects") or []
    normalized_projects: list[str] = []
    for p in projects:
        if isinstance(p, str):
            normalized_projects.append(p)
        elif isinstance(p, dict):
            title = (p.get("title") or "").strip()
            desc = (p.get("description") or "").strip()
            combined = f"{title} — {desc}" if title and desc else title or desc
            if combined:
                normalized_projects.append(combined)
    parsed["top_projects"] = normalized_projects

    # education: str
    education = parsed.get("education")
    if isinstance(education, list):
        parts: list[str] = []
        for e in education:
            if isinstance(e, dict):
                inst  = (e.get("institution") or "").strip()
                degree = (e.get("degree") or "").strip()
                years  = (e.get("years") or e.get("dates") or "").strip()
                line = ", ".join(x for x in [degree, inst, years] if x)
                if line:
                    parts.append(line)
            elif isinstance(e, str):
                if e.strip():
                    parts.append(e.strip())
        parsed["education"] = " | ".join(parts)
    elif not isinstance(education, str):
        parsed["education"] = ""

    layout_obj = ResumeLayout(**layout_raw) if layout_raw else ResumeLayout()

    return CandidateProfile(
        raw_resume=raw_text[:4000],
        extraction_method=method,
        resume_layout=layout_obj,
        **parsed,
    )


@router.post("/socials", response_model=CandidateProfile)
async def enrich_socials(req: SocialsRequest):
    """
    Enrich profile with GitHub (deep: pinned repos, README, contributions)
    and LinkedIn (3-tier: linkedin-api → public HTML → pasted text).
    Both calls run concurrently.
    """
    profile = req.current_profile.model_dump()

    # Screen inputs
    if req.linkedin_text:
        guard = screen_text(req.linkedin_text, source="linkedin_text")
        if not guard.safe:
            req = req.model_copy(update={"linkedin_text": ""})
    if req.bio:
        guard = screen_text(req.bio, source="bio")
        if not guard.safe:
            req = req.model_copy(update={"bio": ""})

    # Run GitHub and LinkedIn enrichment concurrently
    gh_task = (
        _github_agent.enrich(req.github_url)
        if req.github_url else asyncio.sleep(0, result={})
    )
    li_task = (
        _linkedin_agent.enrich(
            linkedin_url=req.current_profile.linkedin_url or "",
            linkedin_text=req.linkedin_text or ""
        )
        if (req.current_profile.linkedin_url or req.linkedin_text) else asyncio.sleep(0, result={})
    )

    gh_data, li_data = await asyncio.gather(gh_task, li_task, return_exceptions=True)

    if isinstance(gh_data, dict):
        profile.update(gh_data)
    if req.github_url:
        profile["github_url"] = req.github_url

    if isinstance(li_data, dict):
        li_structured = li_data.get("linkedin_structured", {})
        if li_structured:
            profile["linkedin_structured"] = li_structured
        # Backfill top-level fields only if not already set from resume parse
        if not profile.get("education") and li_data.get("linkedin_education"):
            profile["education"] = li_data["linkedin_education"]
        if not profile.get("location") and li_data.get("linkedin_location"):
            profile["location"] = li_data["linkedin_location"]
        # Merge LinkedIn skills with existing skills (deduplicated)
        li_skills = li_data.get("linkedin_skills", [])
        if li_skills:
            existing = set(s.lower() for s in profile.get("skills", []))
            new_skills = [s for s in li_skills if s.lower() not in existing]
            profile["skills"] = profile.get("skills", []) + new_skills[:10]
        # Use LinkedIn summary to enrich bio if user didn't provide one
        if not profile.get("bio") and li_data.get("linkedin_summary"):
            profile["bio"] = li_data["linkedin_summary"]

    if req.linkedin_text:
        profile["linkedin_text"] = req.linkedin_text[:3000]
    if req.bio:
        profile["bio"] = req.bio

    return CandidateProfile(**profile)


@router.post("/analyse", response_model=AnalysisResponse)
async def analyse_profile(req: AnalysisRequest):
    """
    Run full analysis pipeline.
    Path 1: LangGraph typed state graph (parse → enrich → merge)
    Path 2: ADK ProfileMerger (LlmAgent + google_search tool)
    Path 3: Original ProfileMerger (direct Gemini)
    """
    profile_dict = req.profile.model_dump()
    prefs_dict   = req.preferences.model_dump()
    result = None

    # Path 1: LangGraph
    try:
        pr = await run_profile_pipeline(
            raw_resume=profile_dict.get("raw_resume", ""),
            preferences=prefs_dict,
            github_url=profile_dict.get("github_url", ""),
            linkedin_text=profile_dict.get("linkedin_text", ""),
            bio=profile_dict.get("bio", ""),
        )
        if pr.get("strength_score", 0) > 0:
            result = {
                "analysis":         pr["analysis"],
                "strength_score":   pr["strength_score"],
                "suggested_skills": pr["suggested_skills"],
                "best_fit_roles":   pr["best_fit_roles"],
            }
    except Exception:
        pass

    # Path 2: ADK
    if not result:
        try:
            adk_merger = get_adk_profile_merger()
            result = await adk_merger.merge_and_analyse(profile_dict, prefs_dict)
        except Exception:
            pass

    # Path 3: Original
    if not result:
        result = await _merger_agent.merge_and_analyse(profile_dict, prefs_dict)

    updated = CandidateProfile(**{**profile_dict, **result, "strength_score": result["strength_score"]})
    return AnalysisResponse(
        analysis=result["analysis"],
        strength_score=result["strength_score"],
        suggested_skills=result.get("suggested_skills", []),
        best_fit_roles=result.get("best_fit_roles", []),
        updated_profile=updated,
    )
