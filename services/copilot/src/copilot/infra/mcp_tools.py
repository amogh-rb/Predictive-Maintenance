"""LangChain tool wrappers around the MCP server's tools (PLAN §2: "It calls
tools through an MCP server"). Each wrapper's `args_schema` exposes only the
fields the model should actually choose (vin, query text, lat/lon, work-order
fields) — `tenant_id`/`role`/`proposed_by` are deliberately absent from the
schema the LLM binds against, and are instead injected here from the values
`copilot/app/agent.py` resolved server-side from the caller's JWT (via the
API's `/v1/copilot/ask` route), before the call ever reaches the MCP server.
This is the guardrail from PLAN §2: "the tenant and role come from the JWT
and are injected server-side" / "there is no raw SQL" — the model only ever
supplies business arguments, never identity.
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Any

from langchain_core.tools import StructuredTool
from mcp import ClientSession
from mcp.client.sse import sse_client
from pydantic import BaseModel, Field

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://mcp-server:9001/sse")


@asynccontextmanager
async def open_session():
    async with sse_client(MCP_SERVER_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def _extract(result: Any) -> Any:
    """MCP tool results carry `structuredContent` (newer FastMCP) or plain
    text content that's JSON (older) — try structured first, fall back to
    parsing the first text block, and finally the raw text itself.
    """
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured
    content = getattr(result, "content", None)
    if content:
        block = content[0]
        text = getattr(block, "text", None)
        if text is not None:
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return text
    return None


class GetFleetRiskArgs(BaseModel):
    limit: int = Field(10, description="max vehicles to return")


class GetVehicleHealthArgs(BaseModel):
    vin: str = Field(..., description="the vehicle's VIN")


class ListAlertsArgs(BaseModel):
    open_only: bool = Field(True, description="only currently open alerts")
    limit: int = Field(20, description="max alerts to return")


class SearchDtcKbArgs(BaseModel):
    query: str = Field(..., description="a symptom description or DTC code")
    k: int = Field(5, description="max results per category")


class FindNearestDepotArgs(BaseModel):
    vehicle_lat: float = Field(..., description="vehicle latitude")
    vehicle_lon: float = Field(..., description="vehicle longitude")


class ProposeWorkOrderArgs(BaseModel):
    vehicle_id: str = Field(..., description="the vehicle's internal UUID (not its VIN)")
    alert_id: str | None = Field(None, description="the alert this work order responds to, if any")


def build_tools(session: ClientSession, tenant_id: str, role: str, proposed_by: str) -> list[StructuredTool]:
    async def _get_fleet_risk(limit: int = 10) -> Any:
        return _extract(await session.call_tool("get_fleet_risk", {"tenant_id": tenant_id, "limit": limit}))

    async def _get_vehicle_health(vin: str) -> Any:
        return _extract(await session.call_tool("get_vehicle_health", {"tenant_id": tenant_id, "vin": vin}))

    async def _list_alerts(open_only: bool = True, limit: int = 20) -> Any:
        return _extract(await session.call_tool(
            "list_alerts", {"tenant_id": tenant_id, "open_only": open_only, "limit": limit}
        ))

    async def _search_dtc_kb(query: str, k: int = 5) -> Any:
        return _extract(await session.call_tool(
            "search_dtc_kb", {"tenant_id": tenant_id, "query": query, "k": k}
        ))

    async def _find_nearest_depot(vehicle_lat: float, vehicle_lon: float) -> Any:
        return _extract(await session.call_tool(
            "find_nearest_depot",
            {"tenant_id": tenant_id, "vehicle_lat": vehicle_lat, "vehicle_lon": vehicle_lon},
        ))

    async def _propose_work_order(vehicle_id: str, alert_id: str | None = None) -> Any:
        return _extract(await session.call_tool(
            "propose_work_order",
            {
                "tenant_id": tenant_id, "role": role, "proposed_by": proposed_by,
                "vehicle_id": vehicle_id, "alert_id": alert_id,
            },
        ))

    return [
        StructuredTool.from_function(
            coroutine=_get_fleet_risk, name="get_fleet_risk",
            description="Top at-risk vehicles for the fleet, ordered by predicted risk score descending.",
            args_schema=GetFleetRiskArgs,
        ),
        StructuredTool.from_function(
            coroutine=_get_vehicle_health, name="get_vehicle_health",
            description="A vehicle's status, open alerts and live twin snapshot, looked up by VIN.",
            args_schema=GetVehicleHealthArgs,
        ),
        StructuredTool.from_function(
            coroutine=_list_alerts, name="list_alerts",
            description="Recent alerts for the fleet, newest first.",
            args_schema=ListAlertsArgs,
        ),
        StructuredTool.from_function(
            coroutine=_search_dtc_kb, name="search_dtc_kb",
            description="Search the DTC knowledge base and past failure signatures for a symptom or code.",
            args_schema=SearchDtcKbArgs,
        ),
        StructuredTool.from_function(
            coroutine=_find_nearest_depot, name="find_nearest_depot",
            description="The nearest depot with a free bay to a given lat/lon.",
            args_schema=FindNearestDepotArgs,
        ),
        StructuredTool.from_function(
            coroutine=_propose_work_order, name="propose_work_order",
            description="Propose a work order for a vehicle. Always requires human approval before any work happens.",
            args_schema=ProposeWorkOrderArgs,
        ),
    ]
