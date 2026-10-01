"""The LangGraph agent (PLAN §2 "Agentic AI": "LangGraph agent using Claude
(model configurable)"). Model swapped to Gemini's free tier for this build —
avoids a paid ANTHROPIC_API_KEY for the hackathon; `GEMINI_MODEL` keeps the
exact model name configurable without a code change, same spirit as PLAN's
own "(model configurable)" note.
"""
from __future__ import annotations

import logging
import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from copilot.domain.guardrails import FALLBACK_REPLY, MAX_ITERATIONS, MAX_OUTPUT_TOKENS
from copilot.infra.mcp_tools import build_tools, open_session

logger = logging.getLogger("copilot.agent")

MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")

SYSTEM_PROMPT = (
    "You are FleetPulse's fleet-maintenance copilot for a fleet manager or technician. "
    "Answer only using the tools provided — never invent a VIN, risk score, alert or DTC. "
    "Present each field's value exactly as the tool returned it — e.g. use `risk_percent` "
    "as-is (it's already a formatted percentage like \"84.4%\"), don't recompute it or show "
    "the raw fraction. If you propose a work order, tell the user it still needs human "
    "approval before any work happens. Format answers as a short markdown list or table, "
    "not a wall of text."
)


def is_configured() -> bool:
    return bool(os.environ.get("GOOGLE_API_KEY"))


def _as_text(content: object) -> str:
    """Newer Gemini models return `AIMessage.content` as a list of content
    blocks (e.g. `[{"type": "text", "text": "..."}]`) rather than a plain
    string that older models/langchain versions returned — join just the
    text parts so `CopilotAskResponse.reply` (a plain str) stays valid.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return ""


async def ask(message: str, tenant_id: str, role: str, proposed_by: str) -> str:
    if not is_configured():
        return FALLBACK_REPLY

    try:
        model = ChatGoogleGenerativeAI(model=MODEL_NAME, max_output_tokens=MAX_OUTPUT_TOKENS, temperature=0)
        async with open_session() as session:
            tools = build_tools(session, tenant_id, role, proposed_by)
            agent = create_react_agent(model, tools=tools)
            result = await agent.ainvoke(
                {"messages": [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=message)]},
                config={"recursion_limit": MAX_ITERATIONS},
            )
        final = result["messages"][-1]
        return _as_text(getattr(final, "content", None)) or FALLBACK_REPLY
    except Exception:
        logger.exception("copilot ask failed for tenant=%s, falling back to stub reply", tenant_id)
        return FALLBACK_REPLY
