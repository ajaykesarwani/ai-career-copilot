"""
Agent Observability — structured trace logging for every agent invocation.

Concept from the 5-Day AI Agents course: agents must be observable in
production. Every agent call is logged with timing, success/failure, and
metadata so failures can be diagnosed and agent behaviour can be audited.

This is intentionally dependency-free (no external tracing service required)
so it works in the free tier / local dev without extra setup. Traces are
kept in an in-memory ring buffer and exposed via GET /api/ops/traces for
debugging and the optional eval harness.
"""

from __future__ import annotations
import time
import functools
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger("agent_trace")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

# Ring buffer — last 200 agent calls, enough for a debugging session without
# unbounded memory growth.
_TRACE_BUFFER: deque[dict[str, Any]] = deque(maxlen=200)


def record_trace(agent: str, action: str, duration_ms: int, success: bool, meta: dict | None = None) -> None:
    event = {
        "agent": agent,
        "action": action,
        "duration_ms": duration_ms,
        "success": success,
        "meta": meta or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _TRACE_BUFFER.append(event)
    level = logging.INFO if success else logging.WARNING
    logger.log(level, "agent=%s action=%s success=%s duration_ms=%d meta=%s",
               agent, action, success, duration_ms, meta or {})


def get_traces(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent traces, newest first."""
    return list(_TRACE_BUFFER)[-limit:][::-1]


def get_trace_stats() -> dict[str, Any]:
    """Aggregate stats — success rate and avg latency per agent."""
    by_agent: dict[str, dict[str, Any]] = {}
    for ev in _TRACE_BUFFER:
        a = ev["agent"]
        s = by_agent.setdefault(a, {"calls": 0, "successes": 0, "total_ms": 0})
        s["calls"] += 1
        s["successes"] += int(ev["success"])
        s["total_ms"] += ev["duration_ms"]

    return {
        agent: {
            "calls": s["calls"],
            "success_rate": round(s["successes"] / s["calls"], 2) if s["calls"] else 0,
            "avg_duration_ms": round(s["total_ms"] / s["calls"]) if s["calls"] else 0,
        }
        for agent, s in by_agent.items()
    }


def traced(agent_name: str, action: str = "call"):
    """
    Decorator for agent methods (async). Wraps the call with timing +
    success/failure tracing, without changing the function's behaviour or
    swallowing exceptions — failures are re-raised after being logged so
    upstream fallback logic (already present throughout this app) keeps working.
    """
    def decorator(fn: Callable):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            start = time.monotonic()
            try:
                result = await fn(*args, **kwargs)
                record_trace(agent_name, action, int((time.monotonic() - start) * 1000), True)
                return result
            except Exception as e:
                record_trace(agent_name, action, int((time.monotonic() - start) * 1000), False,
                             meta={"error": str(e)[:200]})
                raise
        return wrapper
    return decorator
