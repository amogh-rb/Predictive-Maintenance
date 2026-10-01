"""Captures real EXPLAIN (ANALYZE) output for PLAN §2's 3 SQL-optimisation
items, before and after, against the live `core` stack's actual seeded data
(not synthetic numbers). Writes docs/evidence/sql/report.md.

"Before" isn't a second database — items 1-2 are approximated by disabling
the planner's use of the new index/view for that one query (the schema
objects added by migration 007 still exist; the naive query just isn't
shaped to use them, or index scans are turned off for that query only),
which is the standard honest way to compare without maintaining two schemas.
Item 3 runs the literal pre-continuous-aggregate query (raw GROUP BY over
`telemetry_fast`) as "before".

Run with the `core` stack up and seeded/backfilled: `make explain`.
"""
from __future__ import annotations

import psycopg

PG = dict(host="localhost", port=5434, dbname="fleetpulse", user="fleetpulse", password="changeme")
TS = dict(host="localhost", port=5433, dbname="telemetry", user="fleetpulse", password="changeme")

OUT_PATH = "docs/evidence/sql/report.md"


def explain(conn: psycopg.Connection, sql: str, params: tuple = ()) -> str:
    rows = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + sql, params).fetchall()
    return "\n".join(r[0] for r in rows)


def main() -> None:
    sections: list[str] = ["# EXPLAIN ANALYZE — before / after (PLAN §2 SQL optimisation)\n"]

    with psycopg.connect(**PG, autocommit=True) as conn:
        tenant_id = conn.execute("SELECT id FROM tenant WHERE name = 'demo'").fetchone()[0]

        # --- Item 1: at-risk list -------------------------------------------------
        sections.append("## 1. At-risk vehicle list\n")
        sections.append(
            "**Before** (OFFSET pagination directly over the raw, ever-growing "
            "`prediction` table — the N+1 \"latest prediction per vehicle\" lookup "
            "this replaced can't even be expressed as a single plan, so this shows "
            "just the listing half of it):\n"
        )
        before_sql = (
            "SELECT vehicle_id, risk_score, failure_type FROM prediction "
            "WHERE tenant_id = %s ORDER BY risk_score DESC OFFSET 100 LIMIT 20"
        )
        sections.append(f"```\n{explain(conn, before_sql, (tenant_id,))}\n```\n")

        sections.append(
            "**After** (migration 007's `vehicle_latest_risk` materialized view + "
            "composite index, keyset — no OFFSET, no per-row lookup):\n"
        )
        after_sql = (
            "SELECT vehicle_id, risk_score, failure_type FROM vehicle_latest_risk "
            "WHERE tenant_id = %s ORDER BY risk_score DESC, vehicle_id DESC LIMIT 20"
        )
        sections.append(f"```\n{explain(conn, after_sql, (tenant_id,))}\n```\n")

        # --- Item 2: open alerts per fleet -----------------------------------------
        sections.append("## 2. Open alerts per fleet\n")
        query = (
            "SELECT id, vehicle_id, failure_type FROM alert "
            "WHERE tenant_id = %s AND closed_at IS NULL ORDER BY opened_at DESC LIMIT 50"
        )
        conn.execute("SET enable_indexscan = off; SET enable_bitmapscan = off;")
        sections.append("**Before** (same query, migration 007's partial index disabled for this plan):\n")
        sections.append(f"```\n{explain(conn, query, (tenant_id,))}\n```\n")
        conn.execute("SET enable_indexscan = on; SET enable_bitmapscan = on;")
        sections.append("**After** (`idx_alert_open_by_tenant` partial index, WHERE closed_at IS NULL):\n")
        sections.append(f"```\n{explain(conn, query, (tenant_id,))}\n```\n")

    with psycopg.connect(**TS, autocommit=True) as conn:
        # --- Item 3: fleet daily summary -------------------------------------------
        sections.append("## 3. Fleet daily summary\n")
        sections.append("**Before** (raw GROUP BY over the `telemetry_fast` hypertable, every query):\n")
        before_sql = (
            "SELECT vin, time_bucket('1 day', ts) AS day, avg(coolant_c), max(coolant_c) "
            "FROM telemetry_fast GROUP BY vin, day ORDER BY day DESC LIMIT 50"
        )
        sections.append(f"```\n{explain(conn, before_sql)}\n```\n")

        sections.append("**After** (`telemetry_fast_daily` continuous aggregate, pre-computed):\n")
        after_sql = "SELECT vin, day, avg_coolant_c, max_coolant_c FROM telemetry_fast_daily ORDER BY day DESC LIMIT 50"
        sections.append(f"```\n{explain(conn, after_sql)}\n```\n")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(sections))
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
