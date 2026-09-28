"""Postgres access for the API. Connects as `fleetpulse_api`
(NOSUPERUSER NOBYPASSRLS, migration 005) — RLS actually applies to this
role, unlike the default superuser POSTGRES_USER every other service uses
for local dev convenience (session 3 PROGRESS note).

Every request gets one transaction with `app.tenant_id` set via
`set_config(..., true)` (transaction-local, matching db/postgres/seed_fleet.py's
own pattern) from the tenant resolved out of the validated JWT — never a
client-supplied value — so RLS silently confines every query in that
transaction to one tenant's rows.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlmodel import Session, create_engine, text

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        user = os.environ.get("API_DB_USER", "fleetpulse_api")
        password = os.environ.get("API_DB_PASSWORD", "changeme")
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT_EXTERNAL", os.environ.get("POSTGRES_PORT", "5432"))
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


@lru_cache(maxsize=64)
def _tenant_id_cached(tenant_name: str) -> str | None:
    # Tenant is a shared, un-RLS'd catalogue table (migration 004 explicitly
    # exempts it), so this lookup is safe to run outside any tenant scope.
    with Session(get_engine()) as session:
        row = session.execute(
            text("SELECT id FROM tenant WHERE name = :name"), {"name": tenant_name}
        ).first()
        return str(row[0]) if row else None


def resolve_tenant_id(tenant_name: str) -> str | None:
    return _tenant_id_cached(tenant_name)
