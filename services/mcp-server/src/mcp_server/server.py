"""The MCP server itself (PLAN §2 "Agentic AI": "It calls tools through an
MCP server"). Each `@mcp.tool()` function's parameter list is exactly what
the LLM sees and can fill in — `tenant_id`/`role`/`proposed_by` are present
so the copilot can pass them, but the copilot always overwrites whatever
value the model produced for those three fields with the value it resolved
server-side from the caller's JWT before dispatching the call (see
`services/copilot/src/copilot/app/agent.py`), so a tenant/role/identity the
LLM invents in its own output is never trusted. Everything else (vin, query
text, lat/lon, work order fields) is genuinely model-chosen.
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from mcp_server.app import tools

PORT = int(os.environ.get("MCP_SERVER_PORT", 9001))
mcp = FastMCP("fleetpulse-mcp", host="0.0.0.0", port=PORT)


@mcp.tool()
def get_fleet_risk(tenant_id: str, limit: int = 10) -> list[dict]:
    """Top at-risk vehicles for the tenant, ordered by predicted risk score
    descending. Each result's `risk_percent` is already formatted (e.g.
    "84.4%") — present it exactly as given, don't recompute or reformat it."""
    return tools.get_fleet_risk(tenant_id, limit)


@mcp.tool()
def get_vehicle_health(tenant_id: str, vin: str) -> dict:
    """A single vehicle's status, open alerts, and live twin snapshot, looked up by VIN."""
    return tools.get_vehicle_health(tenant_id, vin)


@mcp.tool()
def list_alerts(tenant_id: str, open_only: bool = True, limit: int = 20) -> list[dict]:
    """Recent alerts for the tenant's fleet, newest first."""
    return tools.list_alerts(tenant_id, open_only, limit)


@mcp.tool()
def search_dtc_kb(tenant_id: str, query: str, k: int = 5) -> dict:
    """Nearest-neighbour search over the DTC knowledge base and past failure
    signatures for a free-text query (e.g. a symptom description or DTC code)."""
    return tools.search_dtc_kb(tenant_id, query, k)


@mcp.tool()
def find_nearest_depot(tenant_id: str, vehicle_lat: float, vehicle_lon: float) -> dict | None:
    """The nearest depot to a lat/lon that currently has a free bay."""
    return tools.find_nearest_depot(tenant_id, vehicle_lat, vehicle_lon)


@mcp.tool()
def propose_work_order(
    tenant_id: str, role: str, proposed_by: str, vehicle_id: str, alert_id: str | None = None
) -> dict:
    """Propose a work order for a vehicle. Goes to a human approval queue —
    this never creates an approved work order by itself."""
    return tools.propose_work_order(tenant_id, role, proposed_by, vehicle_id, alert_id)


def run() -> None:
    mcp.run(transport="sse")
