"""
Agent 6 — Interview Coach
Context-aware career coaching with 4 modes.
"""

from .base import BaseAgent
from utils.observability import traced
from utils.guardrails import screen_text, sanitize_for_prompt

SYSTEM_PROMPTS = {
    "general": (
        "You are an expert career coach with 20 years of experience helping tech professionals "
        "land roles at top companies. Give actionable, specific advice. Keep responses concise "
        "(3-5 paragraphs max), practical, and encouraging. Use bullet points sparingly."
    ),
    "technical": (
        "You are a technical interview coach specialising in ML/AI, software engineering, and "
        "system design roles. Give concrete examples, suggest code patterns when relevant, and "
        "coach on both breadth and depth. Call out common mistakes interviewers watch for."
    ),
    "behavioral": (
        "You are a behavioral interview expert. Help candidates craft compelling STAR-method answers, "
        "identify their most powerful career stories, and coach on delivery and confidence. "
        "Be encouraging but give honest feedback. Ask follow-up questions to draw out specifics."
    ),
    "salary": (
        "You are a compensation negotiation specialist. Provide specific scripts, anchoring tactics, "
        "counter-offer strategies, and market benchmarks. Be direct about numbers and tactics. "
        "Never suggest accepting the first offer without negotiating."
    ),
}


class CoachAgent(BaseAgent):
    name = "CoachAgent"

    @traced("CoachAgent", "respond")
    async def respond(self, messages: list[dict], mode: str, profile: dict | None) -> str:
        # Guardrail: screen the latest user turn before it drives agent behaviour.
        # Free-text coach input is the most exposed surface in the app (it's the
        # one field a user types directly, repeatedly, without any structure),
        # so this is where injection screening matters most.
        if messages:
            last = messages[-1]
            if last.get("role") == "user":
                guard = screen_text(last["content"], source="coach_chat")
                if not guard.safe:
                    return (
                        "I can't process that message as written — it contains content "
                        "that looks like an attempt to override my instructions rather than "
                        "a career question. Feel free to rephrase and I'm happy to help!"
                    )

        system = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["general"])

        # Inject candidate context into system prompt
        if profile and profile.get("name"):
            context = (
                f"\n\nCANDIDATE CONTEXT (use to personalise advice):\n"
                f"Name: {profile.get('name')}\n"
                f"Title: {profile.get('title')}\n"
                f"Skills: {', '.join(profile.get('skills', [])[:10])}\n"
                f"Experience: {profile.get('years_exp', 0)} years\n"
                f"Target roles: {profile.get('preferences', {}).get('roles', 'not specified')}\n"
                f"Summary: {profile.get('summary', '')}"
            )
            system += context

        return await self.call(
            [{"role": m["role"], "content": m["content"]} for m in messages[-12:]],
            system=system,
            max_tokens=800,
        )
