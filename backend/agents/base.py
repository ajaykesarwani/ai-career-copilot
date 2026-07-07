"""
Base agent — wraps Google Gemini client with retries and JSON helper.
All specialised agents inherit from this.
"""

import os
import re
import json
import asyncio
from typing import Optional
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

_configured = False

def _ensure_configured():
    global _configured
    if not _configured:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")
        genai.configure(api_key=api_key)
        _configured = True

# Model is configurable via GEMINI_MODEL since Google retires Gemini model
# IDs on a rolling basis (see https://ai.google.dev/gemini-api/docs/deprecations).
# gemini-2.0-flash was retired June 1, 2026 — gemini-2.5-flash is the current
# supported default. Override with GEMINI_MODEL if Google ships a newer one.
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

def _get_model(system: Optional[str] = None) -> genai.GenerativeModel:
    _ensure_configured()
    kwargs = {}
    if system:
        kwargs["system_instruction"] = system
    return genai.GenerativeModel(MODEL, **kwargs)


async def _call_gemini(
    messages: list[dict],
    max_tokens: int = 1500,
    system: Optional[str] = None,
) -> str:
    model = _get_model(system)

    # Convert OpenAI-style messages to Gemini format
    # Gemini uses 'user'/'model' roles and a flat conversation
    gemini_history = []

    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        content = m["content"]

        if role == "user":
            gemini_history.append({"role": "user", "parts": [content]})
        else:
            gemini_history.append({"role": "model", "parts": [content]})

    # If history has items, use chat; otherwise single generate
    if len(gemini_history) > 1:
        # Pop last user message to send as the actual prompt
        chat_history = gemini_history[:-1]
        last_msg = gemini_history[-1]["parts"][0]
        chat = model.start_chat(history=chat_history)
        # Run in executor since Gemini SDK is sync
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: chat.send_message(
                last_msg,
                generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens)
            )
        )
    else:
        prompt = gemini_history[0]["parts"][0] if gemini_history else ""
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens)
            )
        )

    return response.text or ""


async def _call_groq(
    messages: list[dict],
    max_tokens: int = 1500,
    system: Optional[str] = None,
) -> str:
    from groq import AsyncGroq
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable not set")

    # llama-3.1-70b-versatile and llama-3.3-70b-versatile have both been
    # deprecated by Groq; openai/gpt-oss-120b is the current recommended
    # general-purpose model (see https://console.groq.com/docs/deprecations).
    model_name = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    client = AsyncGroq(api_key=api_key)

    groq_messages = []
    if system:
        groq_messages.append({"role": "system", "content": system})
    for m in messages:
        groq_messages.append({"role": m["role"], "content": m["content"]})

    response = await client.chat.completions.create(
        model=model_name,
        messages=groq_messages,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


class BaseAgent:
    """Shared async Gemini wrapper with JSON helper."""

    name: str = "BaseAgent"
    system: str = "You are a helpful AI assistant."

    async def call(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1500,
        system: Optional[str] = None,
    ) -> str:
        sys_prompt = system or self.system

        try:
            return await _call_gemini(messages, max_tokens=max_tokens, system=sys_prompt)
        except ResourceExhausted as e:
            # Gemini quota exceeded -> fall back to Groq if available
            if os.getenv("GROQ_API_KEY"):
                return await _call_groq(messages, max_tokens=max_tokens, system=sys_prompt)
            raise e
        except RuntimeError as e:
            # GEMINI_API_KEY missing -> try Groq
            if "GEMINI_API_KEY" in str(e) and os.getenv("GROQ_API_KEY"):
                return await _call_groq(messages, max_tokens=max_tokens, system=sys_prompt)
            raise e

    async def call_json(self, messages: list[dict], **kwargs) -> dict:
        """Call Gemini and parse JSON from the response."""
        raw = await self.call(messages, **kwargs)
        # Strip markdown fences if present
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Best-effort: extract first {...} or [...] block
            m = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except Exception:
                    pass
            return {}
