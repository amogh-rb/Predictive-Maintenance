from __future__ import annotations

from pydantic import BaseModel


class CopilotAskRequest(BaseModel):
    message: str


class CopilotAskResponse(BaseModel):
    reply: str


class AnalyticsEmbedResponse(BaseModel):
    embed_url: str
