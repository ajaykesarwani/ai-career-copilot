"""
LangGraph Pipeline Orchestrator
================================
Implements the 5-Day AI Agents course concept of an explicit, inspectable
agent pipeline using LangGraph's StateGraph.

Instead of sequential `await agent1(); await agent2()` calls scattered
across FastAPI routers, the entire multi-agent flow is declared as a
directed graph:

    parse_resume → enrich_github → merge_profile → rank_jobs → [END]
                                                  ↗
    (job search node calls Adzuna tool + scores)

Benefits over raw sequential calls:
  - State is typed (TypedDict + Annotated) and validated at every edge
  - Each node is an isolated, testable unit
  - Graph topology is inspectable (visualise via .get_graph().draw_mermaid())
  - Easy to add conditional edges (e.g. skip GitHub if no URL provided)
  - Built-in message accumulation via add_messages for the coach sub-graph
"""

from __future__ import annotations

import os
import asyncio
from typing import Annotated, Optional
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages.ai import AIMessage
from langchain_core.messages.tool import ToolMessage

from utils.observability import record_trace
import time


# ── Typed state schemas ───────────────────────────────────────────────────────

class ProfilePipelineState(TypedDict):
    """State flowing through the profile-building pipeline."""
    # Input
    raw_resume: str
    github_url: Optional[str]
    linkedin_text: Optional[str]
    bio: Optional[str]
    preferences: dict

    # Accumulated by each node
    parsed_profile: dict
    github_enrichment: dict
    merged_profile: dict
    analysis: str
    strength_score: int
    suggested_skills: list[str]
    best_fit_roles: list[str]
    errors: list[str]          # non-fatal errors accumulate here


class JobSearchState(TypedDict):
    """State for the job discovery + ranking sub-graph."""
    profile: dict
    preferences: dict
    raw_jobs: list[dict]        # from Adzuna tool
    ranked_jobs: list[dict]     # after Gemini scoring
    source: str                 # "adzuna" | "ai_estimate"
    errors: list[str]


class CoachState(TypedDict):
    """State for the streaming interview coach sub-graph.

    Uses add_messages reducer so messages accumulate correctly across
    multiple turns without overwriting — the idiomatic LangGraph pattern
    for conversation state.
    """
    messages: Annotated[list, add_messages]
    mode: str
    profile: dict
    last_reply: str


# ── Profile pipeline graph ────────────────────────────────────────────────────

def build_profile_pipeline() -> StateGraph:
    """
    Builds and returns the compiled profile pipeline graph.
    Nodes: parse_resume → enrich_github → merge_profile
    """
    # Import here to avoid circular deps at module load time
    from agents.resume_parser import ResumeParserAgent
    from agents.github_agent import GitHubAgent
    from agents.merger_agent import ProfileMergerAgent

    _parser = ResumeParserAgent()
    _github = GitHubAgent()
    _merger = ProfileMergerAgent()

    async def node_parse_resume(state: ProfilePipelineState) -> dict:
        t = time.monotonic()
        try:
            parsed = await _parser.parse(state["raw_resume"])
            record_trace("ProfileGraph", "parse_resume", int((time.monotonic() - t) * 1000), True)
            return {"parsed_profile": parsed}
        except Exception as e:
            record_trace("ProfileGraph", "parse_resume", int((time.monotonic() - t) * 1000), False, {"error": str(e)})
            return {"parsed_profile": {}, "errors": state.get("errors", []) + [f"resume_parse: {e}"]}

    async def node_enrich_github(state: ProfilePipelineState) -> dict:
        url = state.get("github_url", "")
        if not url:
            return {"github_enrichment": {}}  # conditional skip
        t = time.monotonic()
        try:
            enrichment = await _github.enrich(url)
            record_trace("ProfileGraph", "enrich_github", int((time.monotonic() - t) * 1000), True)
            return {"github_enrichment": enrichment}
        except Exception as e:
            record_trace("ProfileGraph", "enrich_github", int((time.monotonic() - t) * 1000), False, {"error": str(e)})
            return {"github_enrichment": {}, "errors": state.get("errors", []) + [f"github: {e}"]}

    async def node_merge_profile(state: ProfilePipelineState) -> dict:
        profile_data = {
            **state.get("parsed_profile", {}),
            **state.get("github_enrichment", {}),
            "linkedin_text": state.get("linkedin_text", ""),
            "bio": state.get("bio", ""),
        }
        t = time.monotonic()
        try:
            result = await _merger.merge_and_analyse(profile_data, state.get("preferences", {}))
            record_trace("ProfileGraph", "merge_profile", int((time.monotonic() - t) * 1000), True)
            return {
                "merged_profile": {**profile_data, **result},
                "analysis": result["analysis"],
                "strength_score": result["strength_score"],
                "suggested_skills": result["suggested_skills"],
                "best_fit_roles": result["best_fit_roles"],
            }
        except Exception as e:
            record_trace("ProfileGraph", "merge_profile", int((time.monotonic() - t) * 1000), False, {"error": str(e)})
            return {
                "merged_profile": profile_data,
                "analysis": "Analysis unavailable.",
                "strength_score": 0,
                "suggested_skills": [],
                "best_fit_roles": [],
                "errors": state.get("errors", []) + [f"merge: {e}"],
            }

    graph = StateGraph(ProfilePipelineState)
    graph.add_node("parse_resume",   node_parse_resume)
    graph.add_node("enrich_github",  node_enrich_github)
    graph.add_node("merge_profile",  node_merge_profile)

    graph.add_edge(START,            "parse_resume")
    graph.add_edge("parse_resume",   "enrich_github")
    graph.add_edge("enrich_github",  "merge_profile")
    graph.add_edge("merge_profile",  END)

    return graph.compile()


# ── Job search pipeline graph ─────────────────────────────────────────────────

def build_job_pipeline() -> StateGraph:
    """
    Builds the job discovery + ranking sub-graph.
    Nodes: fetch_jobs → score_jobs
    """
    from agents.job_ranker import JobRankerAgent
    from utils import job_search_tool

    _ranker = JobRankerAgent()

    async def node_fetch_jobs(state: JobSearchState) -> dict:
        profile = state["profile"]
        prefs   = state["preferences"]
        query   = (prefs.get("roles") or profile.get("title") or "Software Engineer").split(",")[0].strip()
        location = (prefs.get("locations") or "").strip()
        max_days = int(prefs.get("max_days_old", 21) or 21)

        t = time.monotonic()
        raw: list[dict] = []
        if job_search_tool.is_configured():
            raw = await job_search_tool.search_jobs(
                query=query, location_text=location,
                max_days_old=max_days, results=20,
            )
        source = "adzuna" if raw else "ai_estimate"
        record_trace("JobGraph", "fetch_jobs", int((time.monotonic() - t) * 1000), True,
                     {"count": len(raw), "source": source})
        return {"raw_jobs": raw, "source": source}

    async def node_score_jobs(state: JobSearchState) -> dict:
        raw   = state.get("raw_jobs", [])
        prefs = state["preferences"]
        prof  = state["profile"]
        t = time.monotonic()
        try:
            if raw:
                ranked = await _ranker._score_real_jobs(raw[:16], prof, prefs)
            else:
                ranked = await _ranker._estimate_jobs(
                    prof, prefs,
                    (prefs.get("locations") or ""),
                    prefs.get("location_mode", "any"),
                )
            record_trace("JobGraph", "score_jobs", int((time.monotonic() - t) * 1000), True)
            return {"ranked_jobs": ranked}
        except Exception as e:
            record_trace("JobGraph", "score_jobs", int((time.monotonic() - t) * 1000), False, {"error": str(e)})
            return {"ranked_jobs": raw, "errors": [f"scoring: {e}"]}

    graph = StateGraph(JobSearchState)
    graph.add_node("fetch_jobs",  node_fetch_jobs)
    graph.add_node("score_jobs",  node_score_jobs)

    graph.add_edge(START,         "fetch_jobs")
    graph.add_edge("fetch_jobs",  "score_jobs")
    graph.add_edge("score_jobs",  END)

    return graph.compile()


# ── Coach conversation graph ──────────────────────────────────────────────────

def build_coach_graph() -> StateGraph:
    """
    Stateful coach conversation graph.
    Uses add_messages reducer so conversation history accumulates properly
    across calls — the same pattern shown in the LangGraph course module.
    """
    from langchain_core.tools import tool
    from langgraph.prebuilt import ToolNode

    # Career-advice tool that the coach can call to pull structured suggestions
    @tool
    def get_interview_tips(topic: str) -> str:
        """Return structured interview preparation tips for the given topic.
        Use for: STAR method, salary negotiation, technical questions, behavioural frameworks."""
        tips = {
            "star": "STAR = Situation, Task, Action, Result. Open with context (1 sentence), "
                    "state your specific responsibility, describe 2-3 concrete actions YOU took, "
                    "close with a quantified result. Aim for 90-120 seconds.",
            "salary": "Research market rate first (Levels.fyi, Glassdoor). "
                      "Never give a number first. Use: 'Based on my research and experience, "
                      "I'm targeting £X-Y — is that in range?' Always negotiate equity + benefits.",
            "technical": "Think aloud. Clarify scope before coding. State tradeoffs. "
                         "Start with brute-force, then optimise. Test edge cases. "
                         "Interviewers value communication over perfect code.",
            "behavioural": "Prepare 5-6 core stories that each demonstrate multiple competencies. "
                           "Practice them until fluent but not robotic. "
                           "Tailor which story you tell based on what the question is really asking.",
        }
        for key, text in tips.items():
            if key in topic.lower():
                return text
        return f"Prepare specific examples from your work that demonstrate the asked competency: {topic}"

    tools = [get_interview_tips]
    tool_node = ToolNode(tools)

    def _get_llm():
        """Lazy LLM instantiation — deferred so API key is read at call time, not build time."""
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            google_api_key=os.getenv("GEMINI_API_KEY", ""),
            max_output_tokens=800,
        ).bind_tools(tools)

    def node_coach(state: CoachState) -> dict:
        """Core coach node — calls LangChain ChatGoogleGenerativeAI with bound tools."""
        SYSTEM_PROMPTS = {
            "general": "You are an expert career coach. Be concise, specific, and actionable.",
            "technical": "You are a technical interview coach for ML/AI and software engineering roles.",
            "behavioral": "You are a behavioral interview expert using STAR methodology.",
            "salary": "You are a compensation negotiation specialist. Be direct about numbers and tactics.",
        }
        system = SYSTEM_PROMPTS.get(state.get("mode", "general"), SYSTEM_PROMPTS["general"])
        profile = state.get("profile", {})
        if profile.get("name"):
            system += (f"\n\nCandidate: {profile.get('name')}, {profile.get('title')}, "
                       f"{profile.get('years_exp', 0)} years exp. "
                       f"Skills: {', '.join(profile.get('skills', [])[:8])}")

        from langchain_core.messages import SystemMessage
        llm = _get_llm()
        msgs = [SystemMessage(content=system)] + list(state["messages"])
        response = llm.invoke(msgs)
        return {"messages": [response], "last_reply": response.content or ""}

    def should_use_tool(state: CoachState) -> str:
        """Conditional edge: route to tool_node if the LLM made a tool call."""
        last = state["messages"][-1] if state["messages"] else None
        if last and hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(CoachState)
    graph.add_node("coach",  node_coach)
    graph.add_node("tools",  tool_node)

    graph.add_edge(START,         "coach")
    graph.add_conditional_edges("coach", should_use_tool, {"tools": "tools", END: END})
    graph.add_edge("tools",       "coach")   # tool result feeds back to coach

    return graph.compile()


# ── Singleton compiled graphs (built once at import time) ─────────────────────
# Built lazily to avoid startup failures when the API key isn't yet set.

_profile_pipeline: object | None = None
_job_pipeline: object | None = None
_coach_graph: object | None = None


def get_profile_pipeline():
    global _profile_pipeline
    if _profile_pipeline is None:
        _profile_pipeline = build_profile_pipeline()
    return _profile_pipeline


def get_job_pipeline():
    global _job_pipeline
    if _job_pipeline is None:
        _job_pipeline = build_job_pipeline()
    return _job_pipeline


def get_coach_graph():
    global _coach_graph
    if _coach_graph is None:
        _coach_graph = build_coach_graph()
    return _coach_graph


# ── Convenience async runners (called by routers) ─────────────────────────────

async def run_profile_pipeline(
    raw_resume: str,
    preferences: dict,
    github_url: str = "",
    linkedin_text: str = "",
    bio: str = "",
) -> dict:
    """Run the full profile pipeline and return merged state dict."""
    graph = get_profile_pipeline()
    initial: ProfilePipelineState = {
        "raw_resume": raw_resume,
        "github_url": github_url or None,
        "linkedin_text": linkedin_text,
        "bio": bio,
        "preferences": preferences,
        "parsed_profile": {},
        "github_enrichment": {},
        "merged_profile": {},
        "analysis": "",
        "strength_score": 0,
        "suggested_skills": [],
        "best_fit_roles": [],
        "errors": [],
    }
    result = await graph.ainvoke(initial)
    return result


async def run_job_pipeline(profile: dict, preferences: dict) -> dict:
    """Run the job discovery + ranking pipeline."""
    graph = get_job_pipeline()
    initial: JobSearchState = {
        "profile": profile,
        "preferences": preferences,
        "raw_jobs": [],
        "ranked_jobs": [],
        "source": "ai_estimate",
        "errors": [],
    }
    return await graph.ainvoke(initial)


async def run_coach_turn(
    messages: list[dict],
    mode: str,
    profile: dict,
) -> str:
    """Run one coach conversation turn through the LangGraph coach graph."""
    from langchain_core.messages import HumanMessage, AIMessage as LC_AIMessage

    graph = get_coach_graph()

    # Convert from our internal dict format to LangChain message objects
    lc_messages = []
    for m in messages[-12:]:  # keep last 12 turns in context
        if m["role"] == "user":
            lc_messages.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            lc_messages.append(LC_AIMessage(content=m["content"]))

    initial: CoachState = {
        "messages": lc_messages,
        "mode": mode,
        "profile": profile,
        "last_reply": "",
    }

    result = await graph.ainvoke(initial)
    return result.get("last_reply", "")
