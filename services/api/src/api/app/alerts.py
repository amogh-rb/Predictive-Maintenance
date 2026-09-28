from __future__ import annotations

from typing import Any

from sqlmodel import Session

from api.infra import repositories as repo


def list_alerts(session: Session, open_only: bool, limit: int) -> list[dict[str, Any]]:
    return repo.list_alerts(session, open_only=open_only, limit=limit)
