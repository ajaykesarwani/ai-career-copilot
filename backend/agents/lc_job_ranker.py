"""
LangChain Tool-Calling Job Ranker
===================================
Implements job discovery using the full LangChain tool-calling stack:

  @tool decorated functions (Adzuna search + google_search fallback)
  → ChatGoogleGenerativeAI with .bind_tools()
  → ToolNode for parallel tool dispatch
  → AIMessage / ToolMessage message passing

This is the idiomatic LangChain agentic pattern from the 5-day course:
the LLM decides which tools to call, ToolNode executes them in parallel,
and the results (ToolMessages) flow back to the LLM for final synthesis.

Used as a higher-level alternative to the raw job_ranker.py — routers
can choose which implementation to use based on whether LangChain keys
are configured. Both produce the same output schema.
"""

from __future__ import annotations

import os
import json
import uuid
import asyncio
from typing import Annotated
from typing_extensions import TypedDict

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages.ai import AIMessage
from langchain_core.messages.tool import ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from utils.observability import record_trace
import time


# ── Tool definitions ─────────────────────────────────────────────────────────

@tool
async def search_adzuna_jobs(query: str, location: str = "", max_days_old: int = 21) -> str:
    """Search Adzuna job board for real, recent job postings.
    
    Args:
        query: Role or job title to search for, e.g. 'ML Engineer', 'Data Scientist'
        location: City or region filter, e.g. 'London', 'Berlin', 'New York'. Leave blank for worldwide.
        max_days_old: Maximum age of postings in days (1-60). Default 21 = last 3 weeks.
    
    Returns:
        JSON string containing a list of job posting objects with title, company, location, salary, desc, url.
    """
    from utils import job_search_tool
    jobs = await job_search_tool.search_jobs(
        query=query,
        location_text=location,
        max_days_old=max_days_old,
        results=15,
    )
    record_trace("LCJobTool", "search_adzuna_jobs", 0, True, {"query": query, "location": location, "count": len(jobs)})
    return json.dumps(jobs[:12])


@tool
async def estimate_jobs_for_role(
    role: str,
    skills: str,
    location_preference: str = "Remote",
    seniority: str = "Mid-level",
) -> str:
    """Generate realistic estimated job postings when no live job API is available.
    Use this as a fallback when search_adzuna_jobs returns no results.
    
    Args:
        role: Target job title, e.g. 'Senior ML Engineer'
        skills: Comma-separated key skills, e.g. 'Python, TensorFlow, PyTorch'
        location_preference: Preferred location or 'Remote'
        seniority: Seniority level, e.g. 'Mid-level', 'Senior', 'Staff'
    
    Returns:
        JSON string of estimated job postings (tagged source: ai_estimate)
    """
    # This tool is always available (no external API needed) — it's the LLM's
    # own knowledge used in a structured, auditable way
    return json.dumps([{
        "title": role,
        "company": "Various Companies",
        "location": location_preference,
        "type": "remote" if "remote" in location_preference.lower() else "hybrid",
        "salary": "Competitive",
        "tags": [s.strip() for s in skills.split(",")[:3]],
        "logo": "💼",
        "desc": f"Estimated {seniority} {role} role. Use search_adzuna_jobs for live postings.",
        "posted": "Recently",
        "source": "ai_estimate",
        "date_posted_iso": "",
        "url": "#",
    }])


# ── LangGraph state for the tool-calling ranker ──────────────────────────────

class JobRankerState(TypedDict):
    messages: Annotated[list, add_messages]
    profile: dict
    preferences: dict
    final_jobs: list[dict]


# ── LangChain tool-calling ranker graph ──────────────────────────────────────

def build_lc_job_ranker() -> object:
    """
    Build a LangGraph graph that uses ChatGoogleGenerativeAI with bound tools
    to discover and rank jobs.
    """
    tools = [search_adzuna_jobs, estimate_jobs_for_role]
    tool_node = ToolNode(tools)

    def _get_llm():
        """Lazy — read API key at call time, not module-load time."""
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            google_api_key=os.getenv("GEMINI_API_KEY", ""),
            max_output_tokens=2500,
        ).bind_tools(tools)

    def node_ranker(state: JobRankerState) -> dict:
        """Invoke the LLM — it decides whether to call tools or produce final output."""
        from langchain_core.messages import SystemMessage, HumanMessage

        profile = state["profile"]
        prefs   = state["preferences"]
        query   = (prefs.get("roles") or profile.get("title") or "Software Engineer").split(",")[0].strip()
        location = prefs.get("locations") or ""
        max_days = int(prefs.get("max_days_old", 21) or 21)

        system = (
            "You are a recruitment intelligence system. Search for real job postings using "
            "search_adzuna_jobs. If it returns no results, use estimate_jobs_for_role. "
            "After getting job data, score each posting against the candidate profile (0-100) "
            "and return ONLY a JSON array of job objects with an added 'match' integer field. "
            "Sort by match score descending. Return only the JSON array, no prose."
        )
        user = (
            f"Find and score {query} jobs{' in ' + location if location else ''} "
            f"(last {max_days} days) for this candidate:\n"
            f"Title: {profile.get('title','')}\n"
            f"Skills: {', '.join(profile.get('skills', [])[:12])}\n"
            f"Years experience: {profile.get('years_exp', 0)}\n"
            f"Seniority: {prefs.get('seniority','Mid-level')}\n"
            f"Call search_adzuna_jobs first, then return scored JSON array."
        )

        msgs = state.get("messages", [])
        if not msgs:
            msgs = [HumanMessage(content=f"{system}\n\n{user}")]

        llm = _get_llm()
        response = llm.invoke(msgs)
        return {"messages": [response]}

    def should_continue(state: JobRankerState) -> str:
        """Route to tool_node if the LLM made tool calls, else parse final output."""
        last = state["messages"][-1] if state["messages"] else None
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return "parse_output"

    def node_parse_output(state: JobRankerState) -> dict:
        """Extract the final JSON job list from the last LLM message."""
        last = state["messages"][-1] if state["messages"] else None
        text = last.content if hasattr(last, "content") else ""
        try:
            cleaned = text.replace("```json", "").replace("```", "").strip()
            m = __import__("re").search(r"\[.*\]", cleaned, __import__("re").DOTALL)
            jobs = json.loads(m.group()) if m else []
        except Exception:
            jobs = []

        # Assign stable IDs and ensure required fields are present
        normalised = []
        for j in jobs:
            j.setdefault("id",   f"j_{uuid.uuid4().hex[:8]}")
            j.setdefault("selected", False)
            j.setdefault("source",   "adzuna" if j.get("url", "#") != "#" else "ai_estimate")
            j.setdefault("logo",     "💼")
            j.setdefault("tags",     [])
            j.setdefault("date_posted_iso", "")
            j.setdefault("match",    70)
            j["match"] = int(j["match"])
            normalised.append(j)

        return {"final_jobs": sorted(normalised, key=lambda x: -x["match"])}

    graph = StateGraph(JobRankerState)
    graph.add_node("ranker",       node_ranker)
    graph.add_node("tools",        tool_node)
    graph.add_node("parse_output", node_parse_output)

    graph.add_edge(START,          "ranker")
    graph.add_conditional_edges("ranker", should_continue,
                                 {"tools": "tools", "parse_output": "parse_output"})
    graph.add_edge("tools",        "ranker")   # tool results fed back to LLM
    graph.add_edge("parse_output", END)

    return graph.compile()


# ── Singleton ─────────────────────────────────────────────────────────────────

_lc_ranker: object | None = None

def get_lc_job_ranker():
    global _lc_ranker
    if _lc_ranker is None:
        _lc_ranker = build_lc_job_ranker()
    return _lc_ranker


async def run_lc_job_ranker(profile: dict, preferences: dict) -> list[dict]:
    """Convenience wrapper — runs the LangChain tool-calling ranker graph."""
    t = time.monotonic()
    try:
        graph = get_lc_job_ranker()
        result = await graph.ainvoke({
            "messages": [],
            "profile": profile,
            "preferences": preferences,
            "final_jobs": [],
        })
        jobs = result.get("final_jobs", [])[:12]
        record_trace("LCJobRanker", "run", int((time.monotonic() - t) * 1000), True, {"jobs_found": len(jobs)})
        return jobs
    except Exception as e:
        record_trace("LCJobRanker", "run", int((time.monotonic() - t) * 1000), False, {"error": str(e)})
        return []
