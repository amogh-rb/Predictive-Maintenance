"""One-time (idempotent) bootstrap for Metabase: admin account + two DB
connections (Postgres core, TimescaleDB) via metabase_reporting
(db/postgres/migrations/008_metabase_role.sql, db/timescale/migrations/
005_metabase_role.sql) + a starter "Fleet Overview" dashboard with 4 native-
SQL questions. Metabase has no declarative realm-import file the way
Keycloak does (infra/keycloak/fleetpulse-realm.json), so this scripts its
REST API instead, same spirit as infra/compose/garage-provision.sh /
db/postgres/seed_fleet.py: reproducible via `make metabase-init`, not a
manual click-through.

Run after `docker compose --profile obs up -d metabase` and after
`db/migrate.sh` has applied 008/005 above.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

METABASE_URL = f"http://localhost:{os.environ.get('METABASE_PORT', '3002')}"
ADMIN_EMAIL = os.environ.get("METABASE_ADMIN_EMAIL", "admin@demo.fleetpulse")
ADMIN_PASSWORD = os.environ.get("METABASE_ADMIN_PASSWORD", "changeme123")
ADMIN_FIRST_NAME = "FleetPulse"
ADMIN_LAST_NAME = "Admin"

DB_USER = os.environ.get("METABASE_DB_USER", "metabase_reporting")
DB_PASSWORD = os.environ.get("METABASE_DB_PASSWORD", "changeme")
POSTGRES_HOST_EXTERNAL = os.environ.get("POSTGRES_HOST_EXTERNAL", "localhost")
POSTGRES_PORT_EXTERNAL = int(os.environ.get("POSTGRES_PORT_EXTERNAL", "5434"))
POSTGRES_DB = os.environ.get("POSTGRES_DB", "fleetpulse")
TIMESCALE_HOST_EXTERNAL = os.environ.get("TIMESCALE_HOST_EXTERNAL", "localhost")
TIMESCALE_PORT_EXTERNAL = int(os.environ.get("TIMESCALE_PORT_EXTERNAL", "5433"))
TIMESCALE_DB = os.environ.get("TIMESCALE_DB", "telemetry")

# Metabase runs *inside* the compose network, so its own DB connections must
# use the in-network host:port, not the *_EXTERNAL ones this script (running
# on the host, like seed_fleet.py) connects through for its own setup calls.
PG_DB_HOST = os.environ.get("POSTGRES_HOST", "postgres")
PG_DB_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
TS_DB_HOST = os.environ.get("TIMESCALE_HOST", "timescaledb")
TS_DB_PORT = int(os.environ.get("TIMESCALE_PORT", "5432"))


def _wait_for_health(client: httpx.Client, timeout_s: int = 60) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            resp = client.get("/api/health")
            if resp.status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(2)
    raise SystemExit(f"metabase did not become healthy within {timeout_s}s")


def _try_login(client: httpx.Client) -> str | None:
    # `/api/session/properties`'s `setup-token` doesn't reliably go null
    # after setup (confirmed live: still returned a UUID, and reusing it
    # 403s) — logging in with the known admin creds is the actual signal
    # this script's own prior run already completed setup.
    resp = client.post(
        "/api/session", json={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if resp.status_code != 200:
        return None
    return resp.json()["id"]


def _run_setup(client: httpx.Client) -> str:
    props = client.get("/api/session/properties").json()
    token = props["setup-token"]
    resp = client.post(
        "/api/setup",
        json={
            "token": token,
            "user": {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD,
                "first_name": ADMIN_FIRST_NAME,
                "last_name": ADMIN_LAST_NAME,
            },
            "prefs": {"site_name": "FleetPulse Analytics", "allow_tracking": False},
        },
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _upsert_database(client: httpx.Client, session_id: str, *, name: str, host: str, port: int, dbname: str) -> int:
    headers = {"X-Metabase-Session": session_id}
    existing = client.get("/api/database", headers=headers).json().get("data", [])
    for db in existing:
        if db["name"] == name:
            return db["id"]

    resp = client.post(
        "/api/database",
        headers=headers,
        json={
            "engine": "postgres",
            "name": name,
            "details": {
                "host": host,
                "port": port,
                "dbname": dbname,
                "user": DB_USER,
                "password": DB_PASSWORD,
                "ssl": False,
            },
        },
    )
    resp.raise_for_status()
    return resp.json()["id"]


# vehicle risk uses vehicle_latest_risk (session 6, refreshed via
# `make refresh-risk`), not raw `prediction`, so this reads the same
# up-to-date view the at-risk API endpoint does.
_QUESTIONS = [
    {
        "name": "Fleet risk distribution by failure type",
        "display": "bar",
        "database_key": "core",
        "sql": """
            select failure_type, count(*) as at_risk_vehicles
            from vehicle_latest_risk
            where risk_score >= 0.5
            group by failure_type
            order by at_risk_vehicles desc
        """,
    },
    {
        "name": "Open alerts, last 30 days",
        "display": "line",
        "database_key": "core",
        "sql": """
            select date_trunc('day', opened_at) as day, count(*) as alerts_opened
            from alert
            where opened_at >= now() - interval '30 days'
            group by day
            order by day
        """,
    },
    {
        "name": "Work order mean time to approval (hours)",
        "display": "scalar",
        "database_key": "core",
        "sql": """
            select
                round(avg(extract(epoch from (approved_at - created_at)) / 3600.0)::numeric, 1)
                    as avg_hours_to_approve
            from work_order
            where approved_at is not null
        """,
    },
    {
        "name": "Daily telemetry health trend (coolant/oil)",
        "display": "line",
        "database_key": "telemetry",
        "sql": """
            select
                day,
                avg(avg_coolant_c) as avg_coolant_c,
                avg(avg_oil_kpa) as avg_oil_kpa
            from telemetry_fast_daily
            where day >= now() - interval '30 days'
            group by day
            order by day
        """,
    },
]


def _upsert_question(client: httpx.Client, session_id: str, *, db_id: int, spec: dict) -> int:
    headers = {"X-Metabase-Session": session_id}
    existing = client.get("/api/card", headers=headers).json()
    for card in existing:
        if card["name"] == spec["name"]:
            return card["id"]

    resp = client.post(
        "/api/card",
        headers=headers,
        json={
            "name": spec["name"],
            "display": spec["display"],
            "visualization_settings": {},
            "dataset_query": {
                "type": "native",
                "native": {"query": spec["sql"].strip()},
                "database": db_id,
            },
        },
    )
    resp.raise_for_status()
    return resp.json()["id"]


# Metabase 0.50's dashboard grid is 18 columns wide for a "fixed"-width
# dashboard (the default). 2 columns x 2 rows (9 wide each) so all 4 cards
# are visible without scrolling — the embed iframe fills the viewport height
# (web/src/index.css's .analytics-frame), so a 2x2 grid fits one screen the
# way 4 stacked full-width cards didn't.
_GRID_WIDTH = 18
_CARD_WIDTH = _GRID_WIDTH // 2
_CARD_HEIGHT = 8
_POSITIONS = [(0, 0), (0, _CARD_WIDTH), (_CARD_HEIGHT, 0), (_CARD_HEIGHT, _CARD_WIDTH)]


def _upsert_dashboard(client: httpx.Client, session_id: str, *, name: str, card_ids: list[int]) -> int:
    headers = {"X-Metabase-Session": session_id}
    existing = client.get("/api/dashboard", headers=headers).json()
    for dash in existing:
        if dash["name"] == name:
            dash_id = dash["id"]
            break
    else:
        resp = client.post("/api/dashboard", headers=headers, json={"name": name})
        resp.raise_for_status()
        dash_id = resp.json()["id"]

    # Signed embedding (services/api's analytics router) needs
    # enable_embedding on, not just dashboard existence. `width: "full"`
    # (default is "fixed", a fixed pixel width regardless of the iframe's
    # actual size) stretches the grid to fill the embed iframe instead of
    # leaving dead space around a fixed-size layout — confirmed live, the
    # 2x2 grid otherwise renders far smaller than the iframe it's embedded
    # in.
    client.put(
        f"/api/dashboard/{dash_id}",
        headers=headers,
        json={"enable_embedding": True, "embedding_params": {}, "width": "full"},
    )

    current = client.get(f"/api/dashboard/{dash_id}", headers=headers).json()
    existing_dashcards = {c["card_id"]: c["id"] for c in current.get("dashcards", [])}

    # Always recompute the full 2x2 layout from scratch (not an append-only
    # diff): with a fixed, known set of 4 cards this is simpler and
    # self-healing — re-running after a manual/partial layout change (as
    # happened live while debugging this) converges back to the intended
    # grid instead of layering on top of whatever was there before.
    # POST /api/dashboard/:id/cards doesn't exist in this Metabase version
    # (confirmed live: 404 "API endpoint does not exist") — 0.50 adds/moves
    # cards via one bulk PUT on the dashboard itself; a new card's `id` is a
    # negative placeholder (Metabase's own convention for "not yet assigned"),
    # an existing card's real id keeps it as an update rather than a duplicate.
    new_dashcards = [
        {
            "id": existing_dashcards.get(card_id, -(i + 1)),
            "card_id": card_id,
            "row": row,
            "col": col,
            "size_x": _CARD_WIDTH,
            "size_y": _CARD_HEIGHT,
        }
        for i, (card_id, (row, col)) in enumerate(zip(card_ids, _POSITIONS))
    ]

    resp = client.put(
        f"/api/dashboard/{dash_id}",
        headers=headers,
        json={"dashcards": new_dashcards},
    )
    resp.raise_for_status()
    return dash_id


def _enable_embedding(client: httpx.Client, session_id: str) -> None:
    # Two separate switches, both required — the per-dashboard
    # `enable_embedding` flag set in _upsert_dashboard() only controls
    # whether *that* dashboard is embeddable once embedding is possible at
    # all; this instance-wide setting is what actually turns embedding on
    # (confirmed live: without this, every embed URL 200s but renders
    # "Embedding is not enabled" instead of the dashboard).
    headers = {"X-Metabase-Session": session_id}
    client.put("/api/setting/enable-embedding", headers=headers, json={"value": True})


def main() -> None:
    with httpx.Client(base_url=METABASE_URL, timeout=30.0) as client:
        _wait_for_health(client)

        session_id = _try_login(client)
        if session_id is None:
            session_id = _run_setup(client)
            print("metabase: admin account created")
        else:
            print("metabase: already set up, logged in")

        _enable_embedding(client, session_id)
        print("metabase: instance-wide embedding enabled")

        core_db_id = _upsert_database(
            client, session_id, name="core",
            host=PG_DB_HOST, port=PG_DB_PORT, dbname=POSTGRES_DB,
        )
        telemetry_db_id = _upsert_database(
            client, session_id, name="telemetry",
            host=TS_DB_HOST, port=TS_DB_PORT, dbname=TIMESCALE_DB,
        )
        print(f"metabase: databases ready (core={core_db_id}, telemetry={telemetry_db_id})")

        db_ids = {"core": core_db_id, "telemetry": telemetry_db_id}
        card_ids = [
            _upsert_question(client, session_id, db_id=db_ids[q["database_key"]], spec=q)
            for q in _QUESTIONS
        ]
        print(f"metabase: {len(card_ids)} questions ready")

        dash_id = _upsert_dashboard(client, session_id, name="Fleet Overview", card_ids=card_ids)
        print(f"metabase: dashboard ready (id={dash_id})")


if __name__ == "__main__":
    main()
