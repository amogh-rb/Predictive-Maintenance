"""Postgres access for the MCP server. Connects as the same
`fleetpulse_api` role the API service uses (migration 005: NOSUPERUSER
NOBYPASSRLS) — the copilot's tools must respect RLS exactly like every other
authenticated path, never a superuser bypass. Tenant-scoped tools call
`tenant_session`, which sets `app.tenant_id` for the transaction (mirrors
`services/api/src/api/infra/db.py`); `dtc_kb`/`failure_signature` are shared,
un-RLS'd catalogues (migration 004) so `shared_session` skips that step.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlmodel import Session, create_engine, text

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        user = os.environ.get("API_DB_USER", "fleetpulse_api")
        password = os.environ.get("API_DB_PASSWORD", "changeme")
        host = os.environ.get("POSTGRES_HOST", "postgres")
        port = os.environ.get("POSTGRES_PORT", "5432")
        db = os.environ.get("POSTGRES_DB", "fleetpulse")
        url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


@contextmanager
def tenant_session(tenant_id: str) -> Iterator[Session]:
    session = Session(get_engine())
    try:
        session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def shared_session() -> Iterator[Session]:
    session = Session(get_engine())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
