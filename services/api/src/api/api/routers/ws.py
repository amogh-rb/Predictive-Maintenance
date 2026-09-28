"""WebSocket alerts (PLAN §2 "API": WebSocket alerts). Browsers can't set an
Authorization header on the WS handshake, so the JWT travels as a query
param instead — same validation path as every REST route, just a different
place to read the token from.
"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from api.infra.auth import decode_token
from api.infra.ws_broadcaster import broadcaster

router = APIRouter(tags=["alerts"])


@router.websocket("/v1/ws/alerts")
async def ws_alerts(ws: WebSocket, token: str):
    try:
        user = decode_token(token)
    except Exception:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws.accept()
    await broadcaster.register(ws, user.tenant)
    try:
        while True:
            # Alerts only flow server -> client; this just detects disconnect.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.unregister(ws)
