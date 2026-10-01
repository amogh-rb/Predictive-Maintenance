# ADR 6: Human-in-the-loop copilot over MCP tools

**Status:** accepted

**Decision.** A LangGraph agent calls a FastMCP server of fixed tools: `get_fleet_risk`, `get_vehicle_health`, `list_alerts`, `search_dtc_kb` (pgvector), `find_nearest_depot` (Dijkstra), and `propose_work_order`.

**Guardrails.**
- Tenant and role come from the JWT, resolved server-side; the tool schema shown to the model omits them, so the model cannot supply or override them.
- No raw SQL. Each tool runs under `SET LOCAL app.tenant_id` with the RLS-bound role.
- `propose_work_order` only writes `proposed`; a human must approve. (The approval endpoint exists; there is no UI queue for it yet.)
- Iterations capped at 16; every tool call writes an `audit_log` row; tool output is data.
- Failure of the LLM yields a stub reply, not a 500.

**Deviation.** PLAN named Claude; the build uses Gemini's free tier (`gemini-flash-lite-latest`) to avoid a paid key. The agent shape and MCP boundary are provider-independent. The free tier is quota-limited, so the stub may appear.

**Decision history.** The UI's own scheduling path ("Schedule service") is a direct manager action and bypasses the proposal queue; only the copilot path needs approval.
