"""
Shared Pydantic schemas for the AI Career Copilot API.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, HttpUrl


# ── Profile ──────────────────────────────────────────────────────────────────

class ProfilePreferences(BaseModel):
    roles: str = ""
    locations: str = ""
    location_mode: str = "any"   # "strict" = ONLY that location/remote | "any" = worldwide
    salary: str = ""
    seniority: str = "Mid-level"
    remote: bool = True
    hybrid: bool = True
    onsite: bool = False
    industries: str = ""
    max_days_old: int = 21       # recency window for job search


class ResumeLayout(BaseModel):
    """Visual layout metadata extracted from the uploaded resume.
    Used by doc_export to reproduce the candidate's preferred style."""
    columns: int = 1               # 1 = single column, 2 = two-column
    section_order: list[str] = []  # e.g. ["CONTACT","SUMMARY","EXPERIENCE","SKILLS"]
    has_sidebar: bool = False       # sidebar column for skills/contact
    accent_color: str = ""         # hex detected from headers/lines, e.g. "2C3E50"
    font_style: str = "modern"     # "modern" | "classic" | "creative"
    header_style: str = "centered" # "centered" | "left-aligned" | "banner"
    uses_icons: bool = False        # contact icons detected
    uses_dividers: bool = True      # horizontal rules between sections
    raw_description: str = ""       # free-text Gemini description of the layout


class CandidateProfile(BaseModel):
    name: str = ""
    title: str = ""
    summary: str = ""
    skills: list[str] = []
    years_exp: int = 0
    top_projects: list[str] = []
    github_repos: list[str] = []
    github_repos_rich: list[dict] = []     # structured: [{name, description, stars, topics, languages, last_updated, url, is_pinned}]
    github_languages: list[str] = []
    github_pinned: list[str] = []           # pinned repos with descriptions
    github_readme_summary: str = ""         # summary of profile README if present
    github_contributions: str = ""          # contribution activity summary
    linkedin_text: str = ""
    linkedin_structured: dict = {}          # structured LinkedIn data if scraped
    bio: str = ""
    raw_resume: str = ""
    github_url: str = ""
    # Contact / identity fields
    email: str = ""
    phone: str = ""
    location: str = ""
    address: str = ""
    linkedin_url: str = ""
    education: str = ""
    certifications: list[str] = []
    # Layout extracted from uploaded resume — used to reproduce the style
    resume_layout: ResumeLayout = ResumeLayout()
    preferences: ProfilePreferences = ProfilePreferences()
    strength_score: int = 0
    analysis: str = ""
    extraction_method: str = ""  # "text" | "ocr_vision"


class ParseResumeRequest(BaseModel):
    resume_text: str
    github_url: Optional[str] = None
    linkedin_text: Optional[str] = None
    bio: Optional[str] = None


class SocialsRequest(BaseModel):
    github_url: Optional[str] = None
    linkedin_text: Optional[str] = None
    bio: Optional[str] = None
    current_profile: CandidateProfile


class AnalysisRequest(BaseModel):
    profile: CandidateProfile
    preferences: ProfilePreferences


class AnalysisResponse(BaseModel):
    analysis: str
    strength_score: int
    suggested_skills: list[str]
    best_fit_roles: list[str]
    updated_profile: CandidateProfile


# ── Jobs ─────────────────────────────────────────────────────────────────────

class Job(BaseModel):
    id: str
    title: str
    company: str
    location: str
    type: str           # remote | hybrid | onsite
    salary: str
    match: int          # 0-100
    tags: list[str]
    logo: str
    desc: str
    posted: str
    date_posted_iso: str = ""   # ISO date for accurate recency sorting/filtering
    url: str = "#"
    selected: bool = False
    source: str = "ai_estimate"   # "adzuna" | "ai_estimate" — transparency on data provenance


class JobSearchRequest(BaseModel):
    profile: CandidateProfile
    filter_type: Optional[str] = None
    filter_match: Optional[str] = None


class JobSearchResponse(BaseModel):
    jobs: list[Job]
    total: int


# ── Applications ──────────────────────────────────────────────────────────────

class ApplicationDocs(BaseModel):
    resume: str
    cover: str
    notes: str


class GenerateDocsRequest(BaseModel):
    job: Job
    profile: CandidateProfile


class GenerateDocsResponse(BaseModel):
    docs: ApplicationDocs
    job_id: str


class ExportDocRequest(BaseModel):
    """Request to render a generated text document into a formatted file."""
    doc_type: str        # "resume" | "cover"
    format: str           # "pdf" | "docx"
    content: str           # the generated text (resume or cover letter)
    profile: CandidateProfile
    job: Optional[Job] = None
    # When present, doc_export will try to reproduce the candidate's layout
    resume_layout: Optional[ResumeLayout] = None


class QueueItem(BaseModel):
    id: str
    job: Job
    status: str = "pending"   # pending | ready | done
    docs: Optional[ApplicationDocs] = None


# ── Coach ────────────────────────────────────────────────────────────────────

class CoachMessage(BaseModel):
    role: str   # user | assistant
    content: str


class CoachRequest(BaseModel):
    messages: list[CoachMessage]
    mode: str = "general"   # general | technical | behavioral | salary
    profile: Optional[CandidateProfile] = None


class CoachResponse(BaseModel):
    reply: str


# ── Agent Ops: Guardrails, Evaluation, Observability ─────────────────────────

class GuardrailResult(BaseModel):
    safe: bool
    reason: str = ""
    flagged_categories: list[str] = []


class AgentTraceEvent(BaseModel):
    agent: str
    action: str
    duration_ms: int
    success: bool
    meta: dict = {}
