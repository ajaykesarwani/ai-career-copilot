"""
Ops router — agent observability, evaluation, and graph inspection.

New endpoints added for ADK + LangGraph integration:
  GET  /api/ops/traces          — agent call ring buffer
  GET  /api/ops/stats           — per-agent success rate / avg latency
  GET  /api/ops/graph/profile   — LangGraph profile pipeline as Mermaid diagram
  GET  /api/ops/graph/jobs      — LangGraph job pipeline as Mermaid diagram
  GET  /api/ops/graph/coach     — LangGraph coach graph as Mermaid diagram
  POST /api/ops/eval/cover-letter  — rubric scoring (heuristic)
  POST /api/ops/eval/resume        — rubric scoring (heuristic)
  POST /api/ops/eval/jobs          — rubric scoring (heuristic)
  POST /api/ops/eval/cover-adk     — rubric scoring via ADK BuiltInCodeExecutor
  GET  /api/ops/agents             — list of all registered agent implementations
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import APIRouter
from utils import observability, eval_harness
from agents import (
    get_profile_pipeline, get_job_pipeline, get_coach_graph,
    get_adk_eval,
)

router = APIRouter()


@router.get("/traces")
async def get_traces(limit: int = 50):
    """Most recent agent call traces — timing, success/failure, per call."""
    return {"traces": observability.get_traces(limit)}


@router.get("/stats")
async def get_stats():
    """Aggregate per-agent success rate and average latency."""
    return {"stats": observability.get_trace_stats()}


@router.get("/agents")
async def list_agents():
    """Enumerate all registered agent implementations and their frameworks."""
    return {
        "agents": [
            {"name": "ResumeParserAgent",    "framework": "google-generativeai (direct)",  "role": "Resume text extraction"},
            {"name": "AdkResumeParserAgent", "framework": "google-adk LlmAgent",           "role": "Resume parsing (primary)"},
            {"name": "GitHubAgent",          "framework": "google-generativeai (direct)",  "role": "GitHub API enrichment"},
            {"name": "ProfileMergerAgent",   "framework": "google-generativeai (direct)",  "role": "Profile merge (fallback)"},
            {"name": "AdkProfileMergerAgent","framework": "google-adk LlmAgent + google_search", "role": "Profile merge (primary)"},
            {"name": "JobRankerAgent",       "framework": "google-generativeai (direct)",  "role": "Job discovery (fallback)"},
            {"name": "AdkJobSearchAgent",    "framework": "google-adk LlmAgent + AgentTool","role": "Job search (tier 2)"},
            {"name": "LCJobRanker",          "framework": "langchain + langgraph ToolNode","role": "Job search (tier 1)"},
            {"name": "DocumentGeneratorAgent","framework":"google-generativeai (direct)",  "role": "Resume + cover letter generation"},
            {"name": "CoachAgent",           "framework": "google-generativeai (direct)",  "role": "Interview coach (streaming fallback)"},
            {"name": "LangGraphCoach",       "framework": "langchain ChatGoogleGenerativeAI + ToolNode", "role": "Interview coach (primary)"},
            {"name": "AdkEvalAgent",         "framework": "google-adk + BuiltInCodeExecutor","role": "Document quality evaluation"},
        ]
    }


# ── LangGraph graph topology endpoints ───────────────────────────────────────

@router.get("/graph/profile")
async def graph_profile():
    """Return the profile pipeline graph as a Mermaid diagram string."""
    try:
        graph = get_profile_pipeline()
        return {"mermaid": graph.get_graph().draw_mermaid(), "format": "mermaid"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/graph/jobs")
async def graph_jobs():
    """Return the job pipeline graph as a Mermaid diagram string."""
    try:
        graph = get_job_pipeline()
        return {"mermaid": graph.get_graph().draw_mermaid(), "format": "mermaid"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/graph/coach")
async def graph_coach():
    """Return the coach conversation graph as a Mermaid diagram string."""
    try:
        graph = get_coach_graph()
        return {"mermaid": graph.get_graph().draw_mermaid(), "format": "mermaid"}
    except Exception as e:
        return {"error": str(e)}


# ── Evaluation endpoints ──────────────────────────────────────────────────────

@router.post("/eval/cover-letter")
async def eval_cover_letter(payload: dict):
    """Heuristic rubric scoring of a cover letter."""
    return eval_harness.eval_cover_letter(payload.get("text", ""))


@router.post("/eval/resume")
async def eval_resume(payload: dict):
    """Heuristic rubric scoring of a generated resume."""
    return eval_harness.eval_resume_doc(payload.get("text", ""))


@router.post("/eval/jobs")
async def eval_jobs(payload: dict):
    """Heuristic rubric scoring of a job search result set."""
    return eval_harness.eval_job_results(
        payload.get("jobs", []),
        payload.get("location", ""),
        payload.get("location_mode", "any"),
        payload.get("max_days_old", 21),
    )


@router.post("/eval/cover-adk")
async def eval_cover_adk(payload: dict):
    """
    ADK BuiltInCodeExecutor evaluation — the agent writes and runs Python
    to check word count, paragraph structure, and formatting rules.
    More rigorous than the heuristic version; slower (LLM call involved).
    """
    text = payload.get("text", "")
    if not text.strip():
        return {"error": "No text provided"}
    try:
        adk_eval = get_adk_eval()
        result   = await adk_eval.evaluate_cover_letter(text)
        return result
    except Exception as e:
        # Fall through to heuristic eval if ADK fails
        heuristic = eval_harness.eval_cover_letter(text)
        heuristic["note"] = f"ADK eval unavailable ({e}); heuristic used."
        return heuristic
