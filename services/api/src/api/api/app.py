"""FastAPI app factory (PLAN §2 "API": FastAPI + SQLModel, `/v1`, RFC 7807
errors, audit middleware). Kept in `api/api/` (not `api/main.py`) to match
the hexagonal `api -> app -> domain <- infra` layout this repo uses for
every service (CLAUDE.md "Repo layout").
"""
from __future__ import annotations

import http
import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api.api.routers import alerts, analytics, audit, copilot, drivers, maintenance, vehicles, work_orders, ws
from api.infra import db
from api.infra import repositories as repo
from api.infra.otel import instrument
from api.infra.ws_broadcaster import broadcaster

logger = logging.getLogger("api")


def _problem(status_code: int, detail: str) -> JSONResponse:
    # RFC 7807 (application/problem+json), PLAN §2 "API": "RFC 7807 errors".
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content=jsonable_encoder({
            "type": "about:blank",
            "title": http.HTTPStatus(status_code).phrase,
            "status": status_code,
            "detail": detail,
        }),
    )


class AuditMiddleware(BaseHTTPMiddleware):
    """Writes one audit_log row per authenticated request, after the
    response is known (CLAUDE.md: copilot/API audit conventions). Reads
    `request.state.user`, set by `api/deps.py:get_current_user` while the
    route's dependencies ran during `call_next` — unauthenticated requests
    (bad/missing token) never reach that dependency, so they're skipped
    here rather than logged as a fake anonymous actor.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        user = getattr(request.state, "user", None)
        if user is not None:
            try:
                tenant_id = db.resolve_tenant_id(user.tenant)
                if tenant_id:
                    with db.tenant_session(tenant_id) as session:
                        repo.write_audit_log(
                            session,
                            actor=user.email,
                            action=request.method,
                            resource=request.url.path,
                            details={"status_code": response.status_code, "roles": user.roles},
                        )
            except Exception:
                logger.exception("failed to write audit log entry")
        return response


@asynccontextmanager
async def _lifespan(app: FastAPI):
    broadcaster.start()
    yield
    broadcaster.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="FleetPulse API", version="1.0.0", lifespan=_lifespan)
    app.add_middleware(AuditMiddleware)
    # The web app (session 7) is a separate Vite dev server on :5173 talking
    # to this API on :8000 — a real cross-origin browser request, not a
    # same-origin one, so it needs CORS. Origins are the compose/dev
    # defaults; a production deploy would serve web from behind the same
    # ingress and could drop this, but that's outside this POC's scope.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:8080"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException):
        return _problem(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request: Request, exc: RequestValidationError):
        return _problem(422, exc.errors())

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok"}

    app.include_router(vehicles.router)
    app.include_router(alerts.router)
    app.include_router(work_orders.router)
    app.include_router(maintenance.router)
    app.include_router(drivers.router)
    app.include_router(audit.router)
    app.include_router(copilot.router)
    app.include_router(analytics.router)
    app.include_router(ws.router)

    instrument(app)
    return app


app = create_app()
