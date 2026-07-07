import os
import sys
import json
import asyncio
from typing import Optional

# Ensure the backend directory is in the import path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from mcp.server.fastmcp import FastMCP
from agents.resume_parser import ResumeParserAgent
from utils.job_search_tool import search_jobs as adzuna_search_jobs
from agents.coach_agent import CoachAgent

# Initialize FastMCP Server
mcp = FastMCP("AICareerCopilot")

@mcp.tool()
async def parse_resume(resume_text: str) -> str:
    """
    Parses raw resume text and extracts structured details including contact info,
    skills, years of experience, projects, education, and target roles.
    """
    agent = ResumeParserAgent()
    try:
        data = await agent.parse(resume_text)
        return json.dumps(data, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

@mcp.tool()
async def search_jobs(query: str, location: str = "", max_days_old: int = 21) -> str:
    """
    Searches for real, recent job listings on the Adzuna API.
    Args:
        query: The job title or role keyword to search for.
        location: Optional city or country name to filter results.
        max_days_old: Recency window in days (default 21).
    """
    try:
        jobs = await adzuna_search_jobs(
            query=query,
            location_text=location,
            max_days_old=max_days_old,
            results=10
        )
        return json.dumps(jobs, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

@mcp.tool()
async def career_coach_chat(message: str, mode: str = "general") -> str:
    """
    Converses with the AI Career Coach agent for professional guidance.
    Args:
        message: The career or interview question to ask.
        mode: The coaching mode - 'general', 'technical', 'behavioral', or 'salary'.
    """
    agent = CoachAgent()
    try:
        reply = await agent.respond(
            messages=[{"role": "user", "content": message}],
            mode=mode,
            profile=None
        )
        return reply
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    # FastMCP handles stdin/stdout stdio mode by default when run as main
    mcp.run()
