"""
Agent Guardrails — input/output safety screening.

Concept from the 5-Day AI Agents course: any text that flows into an agent's
context from an untrusted source (an uploaded resume file, a scraped job
description, free-text bio) should be screened before being used to drive
agent behaviour. This protects against prompt-injection attempts embedded
in uploaded documents (e.g. "ignore previous instructions and...") and
keeps generated output (resume/cover letter) free of injected content.

Current implementation is a fast, regex-based heuristic screen — zero
latency, zero extra API calls, and free to run on every request. It catches
the overwhelming majority of injection patterns (role-override attempts,
fake system/instruction blocks, exfiltration phrasing) without needing an
LLM call. A natural extension (not yet implemented) would be a secondary
LLM-based classifier for borderline cases the heuristic doesn't confidently
flag, reusing the same Gemini key already configured.
"""

from __future__ import annotations
import re
from models.schemas import GuardrailResult

# Heuristic patterns commonly used in prompt-injection attempts.
_INJECTION_PATTERNS = [
    r"ignore (all )?(previous|prior|above) instructions",
    r"disregard (all )?(previous|prior|above)",
    r"you are now",
    r"system\s*:\s*",
    r"new instructions\s*:",
    r"act as (an? )?(?!.*(engineer|developer|manager|designer|analyst|scientist|researcher|consultant|specialist|coach|writer|architect))",
    r"reveal (your|the) (system )?prompt",
    r"print (your|the) (system )?instructions",
    r"<\s*script",
    r"DAN mode",
    r"jailbreak",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

# Categories flagged separately so callers can decide policy (e.g. allow with
# warning vs hard block).
_PII_HARVEST_PATTERNS = [
    r"send (this|the) (data|profile|resume) to",
    r"email (this|the) (data|profile) to",
]
_PII_RE = re.compile("|".join(_PII_HARVEST_PATTERNS), re.IGNORECASE)


def screen_text(text: str, *, source: str = "user_input") -> GuardrailResult:
    """
    Fast, free heuristic guardrail. Returns safe=False only on clear
    injection attempts — designed to have a very low false-positive rate
    so normal resumes/bios are never blocked.
    """
    if not text or not text.strip():
        return GuardrailResult(safe=True)

    flagged = []
    if _INJECTION_RE.search(text):
        flagged.append("prompt_injection")
    if _PII_RE.search(text):
        flagged.append("data_exfiltration_attempt")

    if flagged:
        return GuardrailResult(
            safe=False,
            reason=f"Content from {source} matched suspicious pattern(s): {', '.join(flagged)}",
            flagged_categories=flagged,
        )
    return GuardrailResult(safe=True)


def sanitize_for_prompt(text: str, max_len: int = 8000) -> str:
    """
    Defensive sanitisation applied before interpolating untrusted text
    (resume content, job descriptions) into an LLM prompt. Strips characters
    commonly used to break out of prompt structure and caps length so a
    single field cannot dominate the context window.
    """
    if not text:
        return ""
    # Neutralise triple-backtick fences and explicit role markers that could
    # be used to impersonate system/assistant turns inside the prompt.
    cleaned = text.replace("```", "'''")
    cleaned = re.sub(r"(?im)^\s*(system|assistant)\s*:", r"[\1]:", cleaned)
    return cleaned[:max_len]


def screen_output(text: str) -> GuardrailResult:
    """
    Output-side guardrail — runs on generated resume/cover-letter/job text
    before it's returned to the user, to catch cases where injected
    instructions in the input leaked into the model's output (e.g. the
    model echoing "ignore previous instructions" back, or emitting
    suspicious URLs/script tags).
    """
    if not text:
        return GuardrailResult(safe=True)

    if re.search(r"<\s*script", text, re.IGNORECASE):
        return GuardrailResult(safe=False, reason="Generated output contained a script tag",
                                flagged_categories=["unsafe_markup"])
    if _INJECTION_RE.search(text[:500]):  # leakage usually shows up early
        return GuardrailResult(safe=False, reason="Generated output echoed an injected instruction",
                                flagged_categories=["injection_leakage"])
    return GuardrailResult(safe=True)
