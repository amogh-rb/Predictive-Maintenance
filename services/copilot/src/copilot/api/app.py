"""Internal HTTP surface the FastAPI `api` service calls
(`api/api/routers/copilot.py`) — not reachable from the browser; only `api`
knows this container's hostname (`copilot`, docker-compose `ai` profile).
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from copilot.app.agent import ask


class AskRequest(BaseModel):
    message: str
    tenant: str
    role: str
    proposed_by: str


class AskResponse(BaseModel):
    reply: str


def create_app() -> FastAPI:
    app = FastAPI(title="FleetPulse Copilot", version="1.0.0")

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok"}

    @app.post("/ask", response_model=AskResponse)
    async def ask_route(body: AskRequest) -> AskResponse:
        reply = await ask(body.message, tenant_id=body.tenant, role=body.role, proposed_by=body.proposed_by)
        return AskResponse(reply=reply)

    return app


app = create_app()
