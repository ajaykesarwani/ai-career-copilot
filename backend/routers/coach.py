"""
Coach router — interview coaching via LangGraph coach graph (primary)
with streaming fallback to direct Gemini.

Primary path: run_coach_turn() from pipeline_graph.py
  - Uses ChatGoogleGenerativeAI with bound tools (get_interview_tips)
  - Full LangGraph StateGraph with add_messages reducer
  - Conditional edge routes to ToolNode when LLM makes tool calls
  - AIMessage / ToolMessage flow through the graph

Streaming path (/coach/stream): direct Gemini streaming SDK
  - LangChain streaming is complex to SSE-bridge; direct SDK is simpler here
  - Still goes through the same guardrail + observability layer
"""

import sys, os, json, asyncio, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from models.schemas import CoachRequest, CoachResponse
from agents import CoachAgent, run_coach_turn
from utils.guardrails import screen_text
from utils.observability import record_trace

router = APIRouter()
_coach = CoachAgent()  # original agent — streaming fallback


@router.post("/chat", response_model=CoachResponse)
async def coach_chat(req: CoachRequest):
    """
    Single-turn coach response.
    Primary: LangGraph coach graph (ChatGoogleGenerativeAI + ToolNode).
    Fallback: original CoachAgent (direct Gemini SDK).
    """
    messages = [m.model_dump() for m in req.messages]
    profile  = req.profile.model_dump() if req.profile else {}

    # Guardrail on latest user message
    if messages and messages[-1].get("role") == "user":
        guard = screen_text(messages[-1]["content"], source="coach_chat")
        if not guard.safe:
            return CoachResponse(reply=(
                "I can't process that message — it looks like an attempt to override "
                "my instructions rather than a career question. Please rephrase!"
            ))

    # ── Primary: LangGraph coach graph ───────────────────────────────────────
    t = time.monotonic()
    try:
        reply = await run_coach_turn(messages, req.mode, profile)
        if reply and reply.strip():
            record_trace("CoachRouter", "langgraph_chat", int((time.monotonic() - t) * 1000), True)
            return CoachResponse(reply=reply)
    except Exception:
        pass

    # ── Fallback: original CoachAgent ────────────────────────────────────────
    try:
        reply = await _coach.respond(messages, req.mode, profile)
        record_trace("CoachRouter", "original_chat", int((time.monotonic() - t) * 1000), True)
        return CoachResponse(reply=reply)
    except Exception as e:
        record_trace("CoachRouter", "chat_failed", int((time.monotonic() - t) * 1000), False, {"error": str(e)})
        return CoachResponse(reply="I'm having trouble connecting right now — please try again in a moment.")


async def _stream_groq(system: str, messages: list[dict], max_tokens: int = 800):
    from groq import AsyncGroq
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable not set")

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
        stream=True,
    )
    async for chunk in response:
        content = chunk.choices[0].delta.content
        if content:
            yield content


@router.post("/stream")
async def coach_stream(req: CoachRequest):
    """
    Streaming coach via direct Gemini SDK (SSE).
    Guardrail + tracing applied before streaming begins.
    """
    import google.generativeai as genai

    messages_raw = [m.model_dump() for m in req.messages]

    # Guardrail
    if messages_raw and messages_raw[-1].get("role") == "user":
        guard = screen_text(messages_raw[-1]["content"], source="coach_stream")
        if not guard.safe:
            async def blocked():
                msg = ("I can't process that message — it looks like an attempt to override "
                       "my instructions. Please rephrase!")
                yield f"data: {json.dumps({'text': msg})}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(blocked(), media_type="text/event-stream")

    api_key = os.getenv("GEMINI_API_KEY")
    use_gemini = True
    if not api_key:
        if os.getenv("GROQ_API_KEY"):
            use_gemini = False
        else:
            raise RuntimeError("GEMINI_API_KEY not set")

    if use_gemini:
        genai.configure(api_key=api_key)

    SYSTEMS = {
        "general":    "You are an expert career coach. Be concise, specific, and actionable.",
        "technical":  "You are a technical interview coach for ML/AI roles.",
        "behavioral": "You are a behavioral interview expert using STAR methodology.",
        "salary":     "You are a compensation negotiation specialist. Be direct about numbers.",
    }
    system = SYSTEMS.get(req.mode, SYSTEMS["general"])
    profile = req.profile.model_dump() if req.profile else {}
    if profile.get("name"):
        system += (
            f"\n\nCandidate: {profile.get('name')}, {profile.get('title')}, "
            f"{profile.get('years_exp', 0)} yrs. "
            f"Skills: {', '.join(profile.get('skills', [])[:8])}"
        )

    if use_gemini:
        gemini_history = []
        for m in messages_raw[:-1]:
            role = "model" if m["role"] == "assistant" else "user"
            gemini_history.append({"role": role, "parts": [m["content"]]})
        last_msg = messages_raw[-1]["content"] if messages_raw else ""
        model = genai.GenerativeModel(
            os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), system_instruction=system
        )

    async def event_stream():
        start = time.monotonic()
        loop  = asyncio.get_event_loop()
        try:
            if use_gemini:
                try:
                    def _stream():
                        chat = model.start_chat(history=gemini_history)
                        return chat.send_message(
                            last_msg,
                            stream=True,
                            generation_config=genai.types.GenerationConfig(max_output_tokens=800),
                        )
                    resp = await loop.run_in_executor(None, _stream)
                    chunks = await loop.run_in_executor(None, lambda: [c.text or "" for c in resp])
                    for text in chunks:
                        if text:
                            yield f"data: {json.dumps({'text': text})}\n\n"
                    record_trace("CoachRouter", "stream", int((time.monotonic() - start) * 1000), True,
                                 {"mode": req.mode})
                except Exception as e:
                    from google.api_core.exceptions import ResourceExhausted
                    is_quota = isinstance(e, ResourceExhausted) or "quota" in str(e).lower() or "429" in str(e)
                    if is_quota and os.getenv("GROQ_API_KEY"):
                        async for text in _stream_groq(system, messages_raw, max_tokens=800):
                            yield f"data: {json.dumps({'text': text})}\n\n"
                        record_trace("CoachRouter", "stream_groq_fallback", int((time.monotonic() - start) * 1000), True,
                                     {"mode": req.mode})
                    else:
                        raise e
            else:
                async for text in _stream_groq(system, messages_raw, max_tokens=800):
                    yield f"data: {json.dumps({'text': text})}\n\n"
                record_trace("CoachRouter", "stream_groq_direct", int((time.monotonic() - start) * 1000), True,
                             {"mode": req.mode})
        except Exception as e:
            record_trace("CoachRouter", "stream_error", int((time.monotonic() - start) * 1000), False,
                         {"error": str(e)[:200]})
            yield f"data: {json.dumps({'text': ' (stream interrupted — please retry)'})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
