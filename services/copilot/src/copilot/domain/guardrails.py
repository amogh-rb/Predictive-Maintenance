"""Pure constants + the stub-fallback text (PLAN §2 "Agentic AI" guardrails:
"iterations and tokens are capped"; PLAN §6.3 session 8: "stub fallback").
No I/O here so this stays trivially unit-testable.
"""
from __future__ import annotations

# LangGraph's create_react_agent recursion_limit: each model-call + tool-call
# round trip costs 2 graph steps, so this caps the agent at a handful of tool
# calls per question, not an unbounded loop against a free-tier quota.
# 8 (4 tool calls) was too tight for an open question like "most urgent vehicle and what should I do":
# it needs the at-risk list, the vehicle, its alerts and the DTC lookup, and LangGraph answered
# "Sorry, need more steps" instead. 16 allows ~8 tool calls and is still a hard cap.
MAX_ITERATIONS = 16

# Gemini free-tier friendly: keeps each reply short, both for latency and to
# stay well inside the free tier's per-minute token quota during a demo.
# 512 was too tight in practice: `gemini-flash-latest` currently resolves to
# a reasoning-capable model that spends part of this budget on internal
# thinking tokens before the visible answer, which then cut off mid-sentence
# (confirmed live) — 2048 leaves enough headroom for that plus a real answer.
MAX_OUTPUT_TOKENS = 2048

FALLBACK_REPLY = (
    "The copilot's language model isn't available right now (no API key configured, "
    "or the free-tier quota was hit). Try the At-Risk Fleet, Vehicle Detail or Live "
    "Alerts screens directly, or ask again in a moment."
)
