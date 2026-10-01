# Analytics (Metabase) — evidence

Refinement built before session 10 (docs/PROGRESS.md). No browser was available in this
environment to click through the web app's Analytics tab directly, so this evidence is real
captured command output against the live running stack (`core` + `obs` profiles), same pattern
as `docs/evidence/{helm,terraform}/README.md` used when a screenshot wasn't the right tool either.

- `metabase_init_run.txt` — a run of `make metabase-init` (`infra/compose/metabase-provision.py`)
  after two real bugs found via the user's own live browser click-through were fixed (see below),
  confirming it's idempotent: "already set up, logged in" instead of re-running Metabase's setup
  wizard, and all 4 questions + the dashboard resolve to their existing ids rather than
  duplicating.
- `live_dashboard_data.txt` — each of the 4 dashboard questions queried directly against the live
  Metabase instance, returning real seeded/backfilled fleet data (not fixtures): 42 at-risk
  vehicles broken down by failure type, 1,906 alerts opened across the last 2 days, real work
  order approval timing, and today's fleet-wide coolant/oil telemetry averages.
- `api_rbac_and_embed.txt` — `GET /v1/analytics/embed-url` through the real `api` container with
  a real Keycloak-issued JWT: `fleet_manager` gets a signed embed URL that itself resolves 200
  when fetched (the actual Metabase iframe target), `technician` gets a real 403 from
  `api/domain/rbac.py`'s `VIEW_ANALYTICS` gate — matching CLAUDE.md's "tenant/role always comes
  from the JWT server-side" convention even though the underlying `metabase_reporting` Postgres
  connection (`db/postgres/migrations/008_metabase_role.sql`) is itself cross-tenant (BYPASSRLS,
  documented trade-off in that migration's comment).

**Two real bugs found from the user's own browser click-through, both fixed:**
1. The page showed Metabase's own "Embedding is not enabled" placeholder instead of the
   dashboard. `_upsert_dashboard()`'s per-dashboard `enable_embedding: true` isn't sufficient —
   Metabase also has a separate, instance-wide `enable-embedding` setting that has to be turned on
   independently (confirmed: the signed URL 200'd the whole time, it just rendered the "not
   enabled" placeholder instead of data). Fixed by having the provisioning script also call
   `PUT /api/setting/enable-embedding {"value": true}`.
2. While chasing (1), found the dashboard actually had **zero** cards attached —
   `POST /api/dashboard/:id/cards` (the endpoint this script originally used to attach cards)
   doesn't exist in Metabase 0.50.31 (`"API endpoint does not exist."`, 404), so every prior
   "4 questions ready" / "dashboard ready" log line was misleading: the questions existed as
   standalone cards, but were never actually wired onto the dashboard. Metabase 0.50 attaches
   cards via one bulk `PUT /api/dashboard/:id` with a `dashcards` array instead. Fixed.
   `.main:has(.analytics-page) { max-width: none; }` also added to `web/src/index.css` — every
   other page's 1100px content cap was wasting horizontal space a Metabase dashboard actually
   needs.

**Layout, per the user's follow-up request** ("all 4 cards visible in one view without
scrolling, 2x2"): `_upsert_dashboard()` now always recomputes a fixed 2x2 grid (each card
half-width, `size_x=9` on the 18-column grid, `size_y=8`, two per row) rather than appending
cards one after another — confirmed live via `GET /api/dashboard/2`:
`(row=0,col=0) (row=0,col=9) / (row=8,col=0) (row=8,col=9)`. Recomputing the full layout every
run rather than diffing is deliberate: it's self-healing against a partial/manual layout change
(exactly what happened live while debugging bug 2 above) instead of layering a new arrangement on
top of stale positions.

**Scaling, per a second follow-up request** ("still a lot of empty space, scale to fit"): the 2x2
grid above rendered correctly but far smaller than the embed iframe — Metabase dashboards default
to `width: "fixed"` (a fixed pixel width regardless of the container), leaving dead space on the
right. Fixed by setting `width: "full"` on the dashboard (`_upsert_dashboard()`), which stretches
the grid to the iframe's actual width. Confirmed live via `GET /api/dashboard/2` (`"width": "full"`,
persists across a rerun) — some residual vertical whitespace below the last row is expected and
left alone: Metabase's embed grid rows are a fixed height per grid unit, not elastic to the
iframe's height, and 2 rows of `size_y=8` already fits one screen without scrolling as asked.

Re-verified live after all fixes: `metabase_init_run.txt` above is from the latest run (also
confirmed idempotent across multiple reruns, no drift), the embed page no longer contains the
"Embedding is not enabled" string, and the dashboard holds all 4 cards in the full-width 2x2 grid
above.
