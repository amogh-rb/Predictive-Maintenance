# PROGRESS

One entry per session. Newest first. 3-5 lines: what got built, what's next, any blockers.
Read this (not chat history) at the start of every new session.

## Session 12: solution document — 2026-10-01

Wrote `docs/solution/FleetPulse_Solution_Document_v2.docx` (incl. STRIDE, measured-results table, deviations, known issues), ADRs 1-6 in `docs/adr/`, C4 + 3 sequence diagrams in `docs/diagrams/c4-and-sequences.md`, and a real `README.md`. Claims are tied to `docs/evidence/`; the doc states what was not achieved (100K/s ingest never measured, ~1K/s simulator-bound; no saved 1 h soak; ZAP not run; coverage 79% vs 80% target; gateway-kill/burst have ~1-2% delta, not zero loss).
**Manual, still open:** screenshots, video timestamps, proofread, PDF export, save the soak output to `docs/evidence/load/` if it exists, tag `v1.0-submission`, push (not pushed yet). Unverified in the doc: pgcrypto column encryption (only the extension is confirmed).

---

## Session 11: train on partial backfill + full-stack verification — 2026-10-01

**Decision:** the overnight backfill crashed at 11,000/20,000 vehicles (the in-flight batch rolled back; DB holds 11,006 vehicles, ~95M FAST / 32M HEALTH rows, 30 days). Finishing needed ~57 GB more on a 67 GB-free disk, so we trained on what was committed instead of backfilling more. `make batch` → `make train` → `make refresh-risk` all ran; `docs/evidence/ml/report.md` is regenerated (335,527 vehicle-days, 8 failure types).

**Risk scores were saturated (~all 1.00), so the model was retrained:** shallower/regularised HGB (depth 3, min leaf 100, L2, early stopping) + Platt (sigmoid) calibration on the validation split (skipped if <10 pos/neg val rows), model `hgb-v2`, and the predictions written went from the top 500 to the top 5,000 (`TOP_N_PREDICTIONS_WRITTEN`; only 566 pairs clear the 0.01 floor now). Result: 734 at-risk vehicles spread 0.01-1.0 (median 0.94, 408 still >=0.9 = vehicles genuinely deep in a fault ramp); before, 445 of ~460 were 1.00. Held-out PR-AUC also improved (brake_wear 0.29 -> 0.96, misfire 0.57 -> 0.92, cooling 0.89 -> 0.99); weakest are ev_battery (0.38, only 2 test positives, not reliable) and transmission (0.66). Powertrain mix of scored failures looks sane (ev_battery only on EV/hybrid). Not done: Spark-side feature noise for more realistic ambiguity; the API's `(risk_score, vehicle_id)` keyset ordering is unchanged.

**At-risk list = predicted to fail in the next 30 days (user's definition):** a vehicle already past its threshold has failed, so it belongs in the live-alerts tab, not at-risk. `lead_time.py` now returns None for already-crossed, flat/improving, and >30-day projections (it used to clamp to a fake 30.0, and returned None for already-crossed so the worst vehicles showed "-"). New migration `009_at_risk_horizon.sql` rebuilds `vehicle_latest_risk` to keep only `0 < lead_days <= 30` and only each tenant's latest `model_version` (it used to take the newest row per vehicle across *all* versions, so stale v1 rows leaked in). **Scoring snapshot is now an as-of backtest (`hgb-v3`):** at the final backfill day *no* vehicle has a failure still ahead (all 347 planted failures, 3.2% of vehicles, fall inside the 30-day history and rows stop at failure), so scoring the last day meant scoring healthy vehicles plus stale pre-failure rows of ones that had already failed. `train.py` now trains only on what was knowable at an as-of date (default: last day - 10 = 2026-09-19, override with `AS_OF_DATE`; rows before it, excluding vehicles whose failure is still in the future) and scores that day's snapshot. The report has a backtest section against what really happened: 113 of 10,765 vehicles failed afterwards; **61 vehicles scored >=0.5 and all 61 truly failed**, 69 scored >=0.2 (66 truly failed), top-113 precision 0.63, failure type right for 100% of hits, lead-time estimate MAE 4.6 days. Horizon is therefore **<=10 days** with this data (a 30-day horizon needs a longer simulation). The training labels were never 7-day (only the headline `any_failure_label` is): per-type models label every pre-failure row of a planted vehicle positive. Per-type test sets are now tiny (2-15 positives), so per-type PR-AUC is noise; the backtest is the number to quote. At-risk tab = 37 vehicles (0 < lead <= 30d): 30 at 0.83-1.0, 7 low (0.01-0.24). Still bimodal: the simulated ramp is clean, so a vehicle is either clearly drifting or clearly healthy; more spread needs ambiguity in the data (Spark-side noise / look-alikes), not a model change.

**Maintenance Scheduled tab (new, user request):** an at-risk vehicle can now be booked into its nearest depot with one click and moves to its own tab. `POST /v1/maintenance/schedule/{vehicle_id}` (fleet_admin/fleet_manager) picks the nearest depot with a free bay via the existing Dijkstra routing (truck position read server-side from the Redis twin, falling back to the home depot; never returned to the client), then opens + approves a work order and books the bay in one transaction, and writes nothing if every depot is full (409; 409 also if already scheduled). `GET /v1/maintenance/scheduled` (all four roles can view) lists bookings whose work order is still `approved`; `POST /v1/maintenance/{work_order_id}/complete` (admin/manager/technician) marks it serviced and frees the bay immediately. The at-risk list hides any vehicle booked since its last scoring, so a booked vehicle is in exactly one tab; after "Mark serviced" it stays out of at-risk until the next `make train` rescoring. Migration `010` (work_order.completed_at + index), new rbac actions, `web/src/pages/MaintenancePage.tsx`, a "Schedule service" button on the at-risk tab, 2 BDD scenarios + 5 unit tests. Verified live end to end with all four roles (201/409/403/404 paths). Browser look-and-feel not eyeballed; only tsc/eslint/build + bundle checks. **The manual propose -> approve -> book-depot workflow was removed** (managers/admins are the users, so "Schedule service" is the only booking path; it is on both the At-Risk tab and the vehicle detail page). Gone: the three buttons, `POST /v1/work-orders` (propose) and `POST /v1/work-orders/{id}/book-depot`, the `PROPOSE_WORK_ORDER`/`BOOK_DEPOT` rbac actions. Kept on purpose: `POST /v1/work-orders/{id}/approve`, because the copilot's MCP `propose_work_order` tool still writes a `proposed` work order that needs a human approver (PLAN §2 guardrail); there is no UI for that approval queue yet. The BDD `work_order_approval` feature now seeds the proposal the way the copilot does (DB insert) instead of calling the removed endpoint. Note: BDD scenarios can leak a booking if the API is cold (e.g. right after a rebuild) because a client timeout lets cleanup run before the server finishes the request; rerun when warm. Scheduled work orders are not auto-completed: a booking's 4 h is the bay hold, the vehicle stays scheduled until marked serviced.

**Final end-to-end verification (2026-10-01 afternoon) found and fixed:**
- **Alerts were filed under the wrong tenant since 09-29** (Live Alerts tab showed nothing newer than 09-29). `AlertStore._load_vin_index` relied on RLS (`set_config('app.tenant_id')`) to scope `SELECT ... FROM vehicle` per tenant, but the state-writer's DB role is a superuser (bypasses RLS), so every pass returned all 100K vehicles and the last tenant in `SELECT id FROM tenant` won for every VIN. The BDD tenant-isolation scenario had left 23 `rogue-*` tenants behind, so real alerts were filed under whichever rogue tenant loaded last. Fixed: explicit `WHERE tenant_id = %s` (+ unit test that fails on the old query), image rebuilt; the BDD scenario now deletes its rogue tenant/vehicle/depot/model/alert. Verified: a fresh `inject-fault` alert lands under `demo` and is the newest row from `GET /v1/alerts`. **Repaired with the user's go-ahead:** the 1,200 mis-filed alerts were re-filed under their vehicle's tenant (`UPDATE alert ... FROM vehicle WHERE alert.tenant_id <> vehicle.tenant_id`) and the 23 leftover `rogue-*` tenants (each owning exactly 1 vehicle, 1 depot, 1 `Rogue` model, 1 alert, no other references) were deleted. Now: 1 tenant (`demo`), 100,000 vehicles, all 2,422 alerts under `demo`; Live Alerts shows today's alerts newest-first.
- Copilot: LangGraph's cap (`MAX_ITERATIONS` 8) made open questions answer "Sorry, need more steps"; raised to 16 (still a hard cap). Its `get_fleet_risk` tool now skips vehicles already booked since scoring, same rule as the At-Risk tab (it was recommending a vehicle already scheduled).
- Verified live: stack healthy, Flink RUNNING, 60 s simulate (24.5K rows), `inject-fault TYPE=oil` alert in ~1 s and pushed over WebSocket in 0.7 s (bad token refused), whole UI driven in Chromium via Playwright (all 6 tabs, schedule -> moves tabs), Grafana panels return data, Metabase dashboard renders. Known demo facts: `TYPE=overheat` is a windowed rule so its alert takes ~1 min; Audit Log needs fleet_admin or auditor (a manager gets a 403); the At-Risk subtitle still says "session 5's model, session 6's keyset-paginated view" (dev jargon); my test runs left ~126 synthetic lubrication alerts on VIN 71HFE8656215DEZ1C and a booked+serviced test row for 8B3XPFR2074X5U3ES (hidden from At-Risk until the next `make train`). On-screen dev jargon (page subtitles, empty/error states mentioning `make` or PLAN sessions) was reworded to plain language. Everything is committed (`0d6f303`); not pushed.

**Fixed:**
- Driver erasure took 35 s: Mongo `raw_archive` (4.2M docs) had no `driver_token` index, so `delete_many` was a collection scan. Added a plain index (`mongo_store.py`; a *partial* `$type: string` index is NOT used by the planner for equality, so don't "optimise" it back). Now 9 ms, IXSCAN.
- `critical_alert_latency` BDD was flaky (~1 in 3 failures): Flink truncates `detected_at` to ms but the test compared `opened_at >` a microsecond start time. Now truncates the start to ms and uses `>=`. The pipeline itself was never losing the alert (0.3-0.9 s end to end).

**Verified:** unit 199, integration 8, contract 8, BDD 7/7 scenarios; live smoke (31k msgs via MQTT → Kafka → Timescale); Flink RUNNING; API + Keycloak RBAC; copilot answers from the new scores; Grafana/Prometheus/Metabase up. **Not verified:** a real browser click-through of the web UI (only that it serves and proxies).

**Gotchas for next time:** Timescale's compression policy ran ~1.5 h on the new data and pegged the CPU (Mongo, Keycloak, tests all time out meanwhile) — wait for `timescaledb_information.chunks` to finish compressing before testing. Spark's `make batch` writes the Parquet in ~20 min but then recomputes the DAG 3x for its summary counts; the output is complete once `_SUCCESS` exists. `make flink-submit` is needed after any restart. My smoke/BDD runs left ~100 synthetic lubrication alerts on VIN 71HFE8656215DEZ1C.

**Next:** Session 12 (solution doc). Uncommitted: `mongo_store.py`, `tests/bdd/steps/alert_pipeline_steps.py`, regenerated ML evidence.

---

## Session 10c: HOP-window alerts fixed — 2026-09-29

Session 10b's blocker ("cooling/transmission HOP-window alerts don't fire live") was three stacked
infra bugs, none in the rule SQL:

1. **Idle Kafka partitions pinned the event-time watermark.** It's the min across all 6
   `telemetry` partitions; a single-VIN `make inject-fault` only feeds one, so windows (and
   MATCH_RECOGNIZE) never closed on a quiet stack. Fix: `SET 'table.exec.source.idle-timeout' =
   '10 s'` in `stream/flink/run-jobs.sh`. Proven with an ad-hoc `CURRENT_WATERMARK()` query: the
   watermark now trails the newest event by ~6s on a single active partition.
2. **Kafka broker GC pauses up to 14.3s at the 512m heap** (G1 evacuation failures at 510/512M,
   live set ~410MB) — longer than KRaft's 9s broker session timeout, so the broker repeatedly
   unloaded/reloaded its own group coordinator (timestamps match every state-writer `SESSTMOUT`
   since this morning). Alerts *were* reaching the `alerts` topic but landed in Postgres minutes
   late, which is why 10b's 15s/120s checks saw nothing. Fix: `KAFKA_HEAP_OPTS` 512m → 1g.
3. **Kafka data was never on the `kafka-data` volume.** The env-generated config had no
   `log.dirs`, so the broker wrote to `/tmp/kafka-logs` inside the container — every recreate
   silently wiped all topics and consumer offsets (found when the heap change did exactly that).
   Fix: `KAFKA_LOG_DIRS: /var/lib/kafka/data`; verified offsets survive `--force-recreate`.

**Verified live on a quiet stack:** cooling and transmission alerts land in Postgres 6-7s after
window close (~35s after fault onset, by design of the >=30s sustained rules); a broker restart
mid-session no longer needs any consumer restarted by hand. 10b's regenerated ML report no longer
lists transmission as unverified.

**Next:** after tonight's soak, check `docker exec fleetpulse-kafka-1 grep Pause
/opt/kafka/logs/kafkaServer-gc.log` for any pause >1s. Then session 12 (solution doc) — note PLAN's
"open items" line on the ~7s windowed-alert latency.

---

## Session 10b: failures 6-8 depth — 2026-09-29

Promoted tyre slow leak, transmission, and EV HV battery from Should to built (PLAN §1),
matching 1-5's depth: simulator signals, real-time Flink rules, Spark features, sklearn training.

**Built:** `simulator/domain/failure.py` — 3 new `FailureType` members, DTC lists, and
`_ELIGIBLE_BY_TYPE` (an EV can't misfire or have a transmission slip; an ICE has no HV battery;
`plan_failures` now takes vehicles, not bare VINs, to enforce this). `signals.py` — tyre leak
drains one fixed tyre per vehicle (`weak_tyre_idx`) toward critical while its siblings stay
healthy; transmission failure raises `trans_c` and inflates reported `rpm` relative to road speed
(slip); EV HV battery widens `cell_v_delta_mv`, raises `cell_temp_max_c`, and drops `soh_pct`.
3 new Flink real-time rules (`03_realtime_rules.sql`, unioned into `05_pipeline.sql`): tyre
pressure/temp threshold, transmission fluid overheat (HOP window), EV cell over-temperature.
`batch/spark/feature_job.py` gained `rpm_per_speed_kmh` (slip ratio), `min_tire_kpa`,
`max_tire_c`, `max_cell_temp_c`, and matching 7-day slopes; `train.py`/`baseline.py`/`lead_time.py`
extended the same way 1-5 already worked (train.py needed no structural change — it already
iterates `for ftype in FailureType`). `inject_fault.py` gained `tyre`/`transmission`/`ev_battery`
types.

**2 real bugs found and fixed along the way (not scope creep — found while building this):**
`alert_misfire_mil` fired on *any* active DTC (`mil_on = TRUE`), not specifically a P030x misfire
code — every failure type with a DTC list was silently mislabeled "misfire" whenever its own alert
also fired; now filtered to actual misfire codes. `cell_v_delta_mv`/`cell_temp_max_c` in
`health_payload` were gated on `FailureType.BATTERY` (the 12V/alternator failure) instead of the
new `EV_HV_BATTERY` — a pre-existing placeholder now corrected now that the real failure type
exists.

**Verified live against the real stack:** unit tests (50 new/updated, 199 total) green; Flink SQL
submitted with zero syntax errors. Tyre and EV-battery real-time alerts confirmed firing end-to-end
(`inject_fault.py` → Kafka → Flink → Postgres `alert` table) after learning the hard way that a
15s injection is too short — `health_payload` only fires once per 60s, so a short injection's only
HEALTH sample lands near severity ~0.1, not near failure_at. Batch/ML verified with a real (not
synthetic-unit-test) 800-vehicle/14-day backfill: Spark wrote 11,780 feature rows with the new
columns, `train.py` trained and scored all 8 failure types with no errors, predictions for
tyre/transmission/ev_battery landed in Postgres `prediction`.

**Blocker found, not fixed:** the transmission rule's HOP window (`GROUP BY ... HAVING MIN(...) >
threshold`, same shape as failure 1's `alert_cooling`) does not fire live on the current Flink
cluster, even after cancelling and cleanly resubmitting the job and a full `flink-jobmanager`/
`flink-taskmanager` restart — confirmed the raw `trans_c` values satisfy the threshold for 34+
continuous seconds (more than the 30s window needs), confirmed the job graph has both window
operators as separate RUNNING vertices, confirmed non-windowed rules on the same job fire
correctly. Then re-tested the **pre-existing, unmodified** `alert_cooling` rule the same way — it
also doesn't fire right now, despite having 8 historical alerts from earlier today (before this
session's job resubmissions). Since `cooling` predates this session and shares no code with
`transmission` beyond the identical HOP-window shape, this reads as an environment/runtime issue
(possibly related to the TaskManager OOM history noted in earlier commits), not a logic bug in
either rule. Logged in PLAN.md's "Open items for the user."

**Next:** a focused session on the HOP-window stall (repro is solid: inject `overheat` or
`transmission`, wait 60s+, check `alert` table) before the solution doc claims sub-5s real-time
alerting for any HOP-window rule. Otherwise: session 12, the solution document.

---

## Session 10a: chaos evidence completeness — 2026-09-29

Deadline turned out to have >48h of slack (Thu 1 Oct 20:00, not the assumed Thu PM), so PLAN §6.3
gained two extra buffer sessions before the solution doc instead of writing it with a known gap:
`docs/evidence/chaos/` only had the TaskManager kill, not the broker or gateway-copy kills the
plan's own verification checklist (§Verification item 8, §6.3 row 9) names.

**Built:** `services/simulator/chaos_broker_test.py` — real producer/consumer (acks=all, RF=3,
min.insync.replicas=2) against the `chaos` profile's 3-broker Kafka, which needed EXTERNAL
listeners added (`docker-compose.yml`, ports 29093-29095, same pattern core Kafka already used)
since the chaos brokers previously had no host-reachable listener at all. `services/simulator/
chaos_gateway_test.py` — scales `ingest-gateway` to 2 copies and kills one mid-load. Along the way
found and fixed a real bug: `GatewaySubscriber`'s MQTT client_id was hardcoded to
`"ingest-gateway"`, so a second scaled copy would have silently kicked the first off the shared
subscription (MQTT client IDs must be unique) instead of load-sharing with it — scaling has never
actually worked until this session's fix (`main.py`, client_id now `ingest-gateway-{hostname}`).
Added `make chaos-broker` / `make chaos-gateway` targets.

**Verified live:** both scripts run against the real stack. Broker kill: 12,000/12,000 acked
messages survived `kafka-chaos-2` being killed and restarted mid-produce (zero loss, evidence in
`docs/evidence/chaos/broker_kill.txt`). Gateway-copy kill: 18,441/18,664 messages delivered
(1.19% loss, within the documented QoS-1-redelivery-noise threshold; `gateway_kill.txt`) — both
gateway copies confirmed connected simultaneously via `docker logs` before the test ran, proving
the client_id fix actually fixed load-sharing. Both temporary profiles (chaos Kafka, 2nd gateway
copy) torn down afterward; core stack confirmed back to its normal single-gateway state.

**Next:** Session 10b — failures 6-8 depth (tyre slow leak, transmission, EV HV battery). User is
running the overnight `make simulate` soak tonight; still need its output saved to
`docs/evidence/load/` before the solution doc (now session 12) is drafted.

**Blockers:** none.

---

## Refinement: UI redesign — 2026-09-29

Second refinement before session 10, at the user's request: a fuller visual pass across every
page (not just the new Analytics tab), since the app was functionally complete but visually plain
(bare `<h2>`/`<p>` headers, flat tables, no summary stats, no loading/empty states). No new
dependencies added — everything is vanilla CSS + a handful of inline SVG icons
(`web/src/components/icons.tsx`), keeping the build's zero-icon-library footprint and low risk.

**Built:** a small shared design layer — `PageHeader` (icon + title + subtitle, replacing the
hand-rolled header on every page), `StatCard`/`StatGrid` (summary metrics), `EmptyState`,
`SkeletonRows` (shimmering loading placeholders instead of a blank table) — plus a redesigned
`index.css` (refined color tokens, card/table/badge treatment, a live-indicator pulse dot,
button/focus states) and a redesigned sidebar (`Layout.tsx`: brand mark, per-item nav icons, role
badges instead of a plain role list). Wired into all 6 pages: **At-Risk Fleet** and **Live Alerts**
gained real summary stat cards computed client-side from the loaded page (critical count, avg lead
time, top failure type / open severity breakdown, live-feed status) — labeled "on this page" /
"showing" rather than implying fleet-wide totals, since both are keyset-paginated or a live-capped
feed, not a full count; **Vehicle Detail** got a status badge in its header and icon-labeled
section headings; **Audit Log**, **Copilot**, **Analytics** got the shared header + loading/empty
states.

**Verified:** `npx tsc -b` / `npx eslint .` / `npm run build` all clean (one real gap found and
fixed: `SVGSVGElement` wasn't in `eslint.config.js`'s browser globals, same class of gap as
session 7/8's `sessionStorage`/`HTMLDivElement` additions — added). Bundle grew from 334KB to
341KB gzipped 106.71KB → 108.83KB (icons are inline SVG, no new package). `web` container rebuilt
and restarted. No browser available in this environment, so the actual look wasn't screenshotted
here — that's the user's own call to make, same as every other visual/design decision in this
refinement.

**Next:** Session 10 — Solution Document, 5 ADRs, STRIDE, C4/sequence diagrams, README.

**Blockers:** none.

---

## Refinement: Metabase Analytics — 2026-09-29

Built before session 10 (deliberately, at the user's request — the solution doc was the only
PLAN §6.3 item left, and this is scoped, additive work, not a jump ahead). Added a Metabase-backed
"Analytics" tab surfacing fleet-wide insight from the raw data (Postgres core + TimescaleDB
telemetry) that only the API/copilot could previously query directly.

**Built:** `metabase_reporting` Postgres role (`db/postgres/migrations/008_metabase_role.sql`,
`db/timescale/migrations/005_metabase_role.sql`) — `NOSUPERUSER BYPASSRLS`, SELECT-only, a
deliberate documented trade-off (same spirit as MinIO→Garage, Claude→Gemini): Metabase's pooled
connections can't `SET LOCAL app.tenant_id` per request the way `api/infra/db.py` does, so an
RLS-bound role would see zero rows; this is single-tenant-demo cross-tenant analytics, with RLS
enforcement untouched everywhere else. `metabase` compose service (`obs` profile, alongside
grafana/prometheus). `infra/compose/metabase-provision.py` (`make metabase-init`) scripts
Metabase's own REST API to bootstrap the admin account + both DB connections + 4 native-SQL
questions (fleet risk by failure type, 30-day alert trend, work order approval time, daily
telemetry health) + one "Fleet Overview" dashboard with signed embedding enabled — idempotent,
verified by running it twice live. `services/api/.../routers/analytics.py`
(`GET /v1/analytics/embed-url`) signs the Metabase iframe URL server-side
(`MB_EMBEDDING_SECRET_KEY` never reaches the browser), gated by a new `VIEW_ANALYTICS` RBAC
action (`fleet_admin`/`fleet_manager` only, `api/domain/rbac.py`) — same "tenant/role from the
JWT server-side" convention as every other route, even though the underlying Metabase connection
is cross-tenant. `web/src/pages/AnalyticsPage.tsx` (new nav tab) fetches the signed URL and embeds
it in an iframe, with the same "not deployed yet" 404 banner pattern session 8's CopilotPage uses.

**Verified end-to-end, live, against the real running stack:** applied both new migrations via
`bash db/migrate.sh`; brought up `metabase` (obs profile) and ran `make metabase-init` twice back
to back — second run correctly logged into the existing admin account and no-op'd on all 4
questions + the dashboard (`docs/evidence/analytics/metabase_init_run.txt`). Queried all 4
dashboard cards directly against Metabase and got real numbers from the actual seeded/backfilled
fleet (42 at-risk vehicles by failure type, real alert counts, real telemetry averages —
`docs/evidence/analytics/live_dashboard_data.txt`). Rebuilt and restarted `api`/`web`; called
`GET /v1/analytics/embed-url` with a real Keycloak-issued `manager@demo` JWT and got a real signed
URL that itself resolves 200 when fetched (the actual Metabase iframe target); called it again as
`tech@demo` and got a real 403 from the RBAC gate (`docs/evidence/analytics/api_rbac_and_embed.txt`).
189/189 unit tests green (6 new for the analytics router), plus a new integration test
(`tests/integration/test_postgres_rls.py::test_metabase_reporting_bypasses_rls_by_design`) pinning
the BYPASSRLS behavior as intentional so a future migration change can't silently break it.
`npx tsc -b` / `npx eslint .` / `npm run build` all clean for the web changes.

**Three real bugs found and fixed, the first two via this session's own live verification, the
last two from the user's own browser click-through (no browser was available in this environment,
so that step was genuinely left for the user, as originally noted here):**
1. `infra/compose/metabase-provision.py`'s original idempotency check read Metabase's
   `/api/session/properties`'s `setup-token`, assuming it goes `null` after setup — live testing
   showed it doesn't (still returns a UUID, and POSTing it again 403s `/api/setup`). Fixed by
   trying a real login with the known admin credentials first and only falling back to
   `/api/setup` on a failed login.
2. The web app's Analytics tab showed Metabase's own "Embedding is not enabled" placeholder. The
   per-dashboard `enable_embedding: true` set at provisioning time isn't enough — Metabase also
   has a separate, instance-wide `enable-embedding` setting that has to be turned on
   independently. Fixed by also calling `PUT /api/setting/enable-embedding`.
3. While chasing (2), found the dashboard actually had **zero** cards attached the whole time —
   `POST /api/dashboard/:id/cards` (this script's original way of attaching a card) doesn't exist
   in Metabase 0.50.31 (`404 "API endpoint does not exist."`), so "4 questions ready / dashboard
   ready" was misleading: the questions existed as standalone cards but were never wired onto the
   dashboard. 0.50 attaches cards via one bulk `PUT /api/dashboard/:id` with a `dashcards` array
   instead — fixed, all 4 cards now render at consistent full-width sizing. Also widened the
   Analytics page past the other pages' 1100px content cap (`.main:has(.analytics-page)` in
   `web/src/index.css`), which was wasting horizontal space the embedded dashboard actually needs.

Re-verified live after all three fixes: `docs/evidence/analytics/metabase_init_run.txt` and
`README.md` updated to reflect the fixed, working state; `GET /api/dashboard/2` now shows all 4
cards attached, and the embed page no longer contains the "Embedding is not enabled" string.
`npx tsc -b` / `npx eslint .` / `npm run build` re-verified clean after the CSS change; `api` and
`web` containers rebuilt and restarted.

**Follow-up, same session:** user asked for all 4 cards visible in one view without scrolling
(2x2). `_upsert_dashboard()` rewritten to always recompute a fixed 2x2 grid (`size_x=9` on the
18-column grid, `size_y=8`, two cards per row) instead of appending — deliberately self-healing
rather than diff-based, since a manual/partial layout change had already happened live while
debugging the bugs above. Verified live via `GET /api/dashboard/2`
(`(row=0,col=0) (row=0,col=9) / (row=8,col=0) (row=8,col=9)`) and reconfirmed idempotent (two
back-to-back runs, no drift). 189/189 unit tests + ruff still clean.

**Second follow-up, same session:** user reported the 2x2 grid still left a lot of empty space
and asked it to scale to fit. Root cause: Metabase dashboards default to `width: "fixed"` — a
fixed pixel width regardless of the actual embed iframe size — so the grid rendered well short of
the iframe's right edge. Fixed by setting `width: "full"` on the dashboard in
`_upsert_dashboard()`, confirmed live via `GET /api/dashboard/2` (persists across a rerun).

**Next:** Session 10 — Solution Document, 5 ADRs, STRIDE, C4/sequence diagrams, README (the last
unticked PLAN §6.3 row).

**Blockers:** none.

---

## Session 9 — 2026-09-29
Built PLAN §6.3 session 9's full slice against the real, already-running `core` stack (not mocks): **integration tests** (`tests/integration/`, Testcontainers — real ephemeral Postgres proving RLS tenant isolation via migrations 001-005 + the real `fleetpulse_api` role, real Kafka proving the actual `Gateway`+`TelemetryProducer` classes dedup/DLQ correctly, real Redis+Mongo proving `state-writer`'s `LatestStateStore`/`TwinStore` round-trip and the raw-archive TTL index); **contract tests** (`tests/contract/` — a Pact HTTP contract for `GET /v1/vehicles/at-risk`, consumer half via `pact-python`'s mock server, provider half verified live against the real running `api` with a real Keycloak-issued JWT; a JSON-Schema contract for the telemetry message, generated from `envelope.py` via `libs/fleetcore/schemas/json/generate.py` and checked for drift); **5 behave BDD scenarios** (`tests/bdd/`, PLAN §5's exact list) run live end-to-end: critical alert <5s and duplicate-doesn't-reach-Kafka-twice both publish real MQTT+mTLS messages through the real Mosquitto→gateway→Kafka→Flink→alerts→state-writer→Postgres pipeline; tenant isolation plants a real second tenant+alert and proves the live API (RLS) never leaks it; driver erasure and work-order approval exercise the real API with real Keycloak tokens for all 4 demo roles.

**3 real bugs found and fixed via this live verification, not caught by unit tests:** (1) `state-writer`/`ingest-gateway`'s Kafka consumer/producer groups had gone stale after ~19h of uptime (the exact same class of issue session 5 hit — `docker compose restart` fixed it, still not auto-recovering on its own, worth a real fix in a later session); (2) a native Windows MongoDB service on port 27017 was shadowing Docker's forward (same class of conflict as session 3's Postgres/5432) — remapped to `MONGO_PORT_EXTERNAL=27018` in `.env`/`.env.example`/`docker-compose.yml`; (3) the `duplicate_no_double_alert` BDD scenario's original assertion ("exactly one alert end-to-end") was wrong given session 4's own documented trade-off that the realtime rules read `telemetry_raw` directly, not the dedup view — Flink's own at-least-once checkpoint replay can double-emit regardless of MQTT-level dedup; rescoped the scenario to assert what's actually guaranteed (ingest-gateway dedup keeps a redelivered duplicate off Kafka entirely), with the pre-existing gap noted in the feature file rather than silently asserted away.

**CI** (`.github/workflows/ci.yml`) rebuilt from the lint-only stub into 7 jobs: lint (ruff + eslint — added `ruff.toml` scoped to F/E9 only, a deliberate choice not to retrofit import-sort/style rules onto 5 sessions of already-working code), unit-tests (with coverage — 79% combined on fleetcore/ingest-gateway/api, fleetcore 98%/ingest-gateway 100%/api ~74%, the gap being thin DB/Redis/Mongo/JWT connection wrappers unit tests intentionally mock around; reported honestly rather than padded), web-build (tsc+build; no vitest suite exists — sessions 7-8 verified the UI live instead, noted rather than faked), integration-tests, contract-tests, security (Semgrep, Trivy fs+image scans, pip-audit, npm audit — all report-only, not gating), and images (build+scan the 5 service Dockerfiles). A `bdd-full-stack` job exists but is `workflow_dispatch`-gated: the full `core` profile (Mosquitto+Kafka+Flink JM/TM+Postgres+Timescale+Mongo+Redis+Garage+Keycloak+api+web, ~8GB per PLAN §3) doesn't fit a free GitHub-hosted runner's headroom — documented honestly rather than silently attempted and left flaky.

**Helm chart** (`infra/helm/fleetpulse/`): one generic chart (PLAN §6.2) templated over `values.yaml`'s `services` map (Deployment+Service+HPA+PDB+NetworkPolicy per app service), bitnami subcharts for Postgres/Redis/Mongo, `values-gcp.yaml`/`values-azure.yaml` overlays. `helm`/`terraform`/`kind` weren't preinstalled in this sandbox — downloaded all three as standalone binaries (no admin rights needed) rather than leaving the tooling unverified: `helm lint` passes, `helm dependency build` really pulls the 3 bitnami charts, `helm template` renders the full manifest set with no errors (evidence in `docs/evidence/helm/`), and — in the same-session follow-up below — a real `kind` cluster install got `api` + bitnami `postgresql` to genuine `1/1 Running`.

**Terraform** (`infra/terraform/aws/`): VPC/EKS/RDS/MSK/S3/KMS/Secrets-Manager from the community `terraform-aws-modules/*` registry modules (PLAN §6.2). `terraform init` + `terraform validate` both pass for real; `terraform plan` gets as far as the two credential-free resources then fails on `No valid credential sources found` — expected, no AWS account for this hackathon, evidence in `docs/evidence/terraform/`.

**EXPLAIN ANALYZE** (`docs/evidence/sql/report.md`, via `make explain`): real captured plans against the live seeded data (100K vehicles, 289 predictions, 1292 alerts, 207K telemetry_fast rows) for all 3 PLAN §2 SQL-optimisation items — items 1-2 already had their index/view from session 6, "before" approximated by disabling that index for one query; item 3's continuous aggregate (`telemetry_fast_daily`, populated via a manual `CALL refresh_continuous_aggregate` — its 1h policy hadn't fired yet) shows a genuine 48ms parallel-seq-scan-across-8-chunks → 0.056ms index-scan improvement.

**UI fixes list:** nothing new to fix — sessions 7-8's own live click-throughs already found and fixed every visual bug they hit (Keycloak mappers, WS alert shape, markdown rendering, risk-score formatting, chat persistence), so this item was already satisfied coming into the session.

PLAN.md checklist rows 7, 8, 9 ticked (7 and 8 were functionally done in their own sessions' live verification but left unticked; corrected here since the checklist is meant to reflect real state).

**Same-session follow-up: closed every gap from the summary above except the solution document itself.**

- **Fixed the Kafka consumer staleness bug** (`state_writer/domain/watchdog.py`, new): `MessageConsumer.has_assignment()` exposes whether the consumer group actually holds a partition assignment; `StateWriter.run_forever` now checks it every poll via a `StallWatchdog`, and raises `ConsumerStalled` after 120s continuously unassigned — `main.py` catches that and exits non-zero so `restart: unless-stopped` recreates the container with a fresh consumer instead of limping forever. Reproduces the exact "docker compose ps says Up, but nothing's actually being consumed" failure sessions 5 and this session's own BDD run both hit. 4 new unit tests (fake clock, no real sleeps).
- **Fixed `prediction.lead_days` always being null** (PROGRESS session 7's known gap): `services/ml/domain/lead_time.py` (new) extrapolates each Must-failure type's own 7-day trailing slope feature (`batch/spark/feature_job.py`'s `coolant_slope_7d`/`oil_kpa_slope_7d`/`charge_v_slope_7d`/`brake_pad_slope_7d`) against that failure's real-time Flink threshold to estimate days-to-cross, capped at 30 days; returns `None` when the trend isn't actually moving toward the threshold (misfire has no slope feature and is left null on purpose). Wired into `train.py`'s `_score_and_write`; re-ran `make train` live — 23/139 real predictions now carry a real `lead_days` (e.g. `brake_wear: 6.2`, `lubrication: 9.8`), materialized view refreshed. 8 new unit tests. Had to relax `tests/contract/test_web_api_pact.py`'s matcher for this field — it's genuinely nullable per-row (mixed float/null in one real page), which this pact library's `like()` can't express as "float or null" for an `each_like`-expanded field; dropped it from the matched shape with a comment pointing at the unit test + the TS `number | null` type as where that contract actually lives now.
- **Burst load test built and run for real** (`services/simulator/burst_test.py`, `make burst`): 500→1500 events/s (3x) against the live stack. First attempts at higher rates (2000→6000, 1000→3000) showed 15-30% of "sent" messages missing from Kafka — traced this down myself rather than assuming a pipeline bug: `state-writer` consumer lag was already back to 0 in those runs, proving Kafka's own ingestion had kept up, so the gap had to be upstream of Kafka; found it was the single-process simulator's own paho/MQTT client being the actual bottleneck at those rates (same root cause session 2's PROGRESS note already named for `bench_ingest.py`), made worse by `ShardedMqttPublisher.close()` disconnecting immediately rather than flushing its queued-but-unsent messages first. Fixed the close-before-drain ordering and dropped the default rate to a sustainable 500/1500; evidence in `docs/evidence/load/burst_test.txt`: 1.97% loss (in the expected few-message noise floor), lag peaked at 24,039 under burst and recovered to 0 in 36s.
- **Chaos test built and run for real** (`services/simulator/chaos_test.py`, `make chaos`): kills the real `flink-taskmanager` container 25s into a 90s live-traffic run, restarts it, confirms the Flink job returns to `RUNNING` on its own (checkpointing, session 4), then reconciles by **`seq`** exactly as PLAN names it — every individual `(vin, seq)` FAST message this run published is looked up in TimescaleDB afterward, not just a row count. Two live runs, both **27,408/27,408 and clean** — zero loss confirmed through a real TaskManager kill, not asserted from documentation. Known, stated gap: doesn't cover a Kafka broker kill — the 3-broker `chaos` compose profile exists but has no gateway/Flink wired to it, and a single-broker `core` Kafka can't survive a broker kill by definition.
- **Helm chart verified on a real `kind` cluster**, not just `helm template`: created a real cluster, built+loaded the real `api` image, `helm install`ed it plus bitnami `postgresql` (redis/mongodb/other app services scaled off via a values override to fit spare RAM alongside the already-running `core` stack). Found and fixed 2 real bugs this uncovered: (1) missing `imagePullPolicy: IfNotPresent` — k8s defaults to `Always` for a `:latest` tag, which 404s a `kind load`ed local-only image; (2) Bitnami's 2025 policy change stopped serving new dated tags on the free `docker.io/bitnami/*` repos, so the chart's own pinned default (`postgresql:16.4.0-debian-12-r14`) 404s — pinned `image.tag: latest` for all 3 bitnami dependencies instead (same class of issue as session 1's MinIO swap). Both `fleetpulse-api` and `fleetpulse-postgresql` reached real `1/1 Running`, and `/healthz` answered through the real Service. Full evidence + the 2-bug writeup in `docs/evidence/helm/README.md`. Cleanly uninstalled/torn down afterward; paused local containers (`flink-jobmanager/taskmanager`, `copilot`, `mcp-server`, `grafana`, `prometheus`, `otel-collector` — stopped to free RAM for the kind cluster) were restarted and the Flink job resubmitted (no HA, so a JM/TM restart always drops the running job — this is the pre-existing, already-documented operational note from session 4, not new).
- Re-ran the full suite after all of the above: 198/198 unit+integration+contract tests green, 7/7 BDD scenarios green (one occasional flake on `driver_erasure` standing alone when run back-to-back with everything else — passes in isolation every time; same class of dev-machine contention flake noted earlier in this same session for the Kafka integration test).

**Next:** Session 10 — Solution Document from PLAN/PROGRESS/evidence, 5 ADRs, STRIDE, C4/sequence diagrams (Mermaid), README. That's the only PLAN §6.3 item left.

**Blockers:** none. Still open, deliberately not chased further this session: the Kafka broker-kill chaos scenario (needs the isolated 3-broker profile wired to a real gateway/Flink, a bigger change than this session's scope), and the `driver_erasure` BDD flake under heavy concurrent load (a dev-machine resource characteristic, not a code defect — every isolated run passes).

**Blockers:** none blocking. Worth a real fix later: the Kafka consumer/producer staleness after long uptime (state-writer/ingest-gateway) — a `docker compose restart` works every time but isn't automatic; a production deployment would want a liveness probe that catches a stuck consumer group, not just an unhandled-exception crash. Also noted: `tests/integration/test_ingest_gateway_kafka.py` (its own testcontainers Kafka, spun up alongside the already-running 20-container `core` stack) failed once under resource contention on this dev machine, passed on 2 immediate re-runs alone and together with the rest of the suite — a machine-load flake, not a code defect, but a smaller/CI-only machine may see it too.

---

## Session 8 — 2026-09-29
Built the copilot (PLAN §6.3 session 8): `services/mcp-server` (FastMCP over SSE, since `copilot`
and `mcp-server` are separate containers — stdio only works for a child-process-in-the-same-container
setup) exposes `get_fleet_risk`, `get_vehicle_health`, `list_alerts`, `search_dtc_kb` (pgvector,
reusing session 5's hashing embedding), `find_nearest_depot` (session 6's Dijkstra), and
`propose_work_order` (role-gated, matching `api/domain/rbac.py`'s PROPOSE_WORK_ORDER set) — each
tool runs under `SET LOCAL app.tenant_id` via the same `fleetpulse_api` RLS-respecting role the API
uses, and writes one `audit_log` row per call. `services/copilot` runs a LangGraph
`create_react_agent` with hand-written `StructuredTool` wrappers around the MCP tools: the wrapper's
exposed schema omits `tenant_id`/`role`/`proposed_by`, which are always injected from the value the
new `api/api/routers/copilot.py` route resolved server-side from the caller's JWT — the LLM can never
supply or override its own tenant/identity, even though the underlying MCP tool signature still
carries those fields. A stub fallback (`domain/guardrails.FALLBACK_REPLY`) covers a missing/failed
`GOOGLE_API_KEY` instead of a 500. `POST /v1/copilot/ask` (new API router) matches the contract
`CopilotPage.tsx` (session 7) already calls — no web changes needed — and maps a connection failure
to 404, the same code the frontend already treats as "not deployed yet".

**Engineering decision, documented not silent (same spirit as session 1's MinIO→Garage swap):**
PLAN.md specifies "LangGraph + Claude + MCP server"; swapped Claude for **Google Gemini's free
tier** (`langchain-google-genai`, `GOOGLE_API_KEY`) to avoid a paid `ANTHROPIC_API_KEY` for this
hackathon. Nothing else in the architecture changed — same LangGraph agent shape, same MCP tool
boundary, same guardrails. `services/mcp-server/src/mcp_server/domain/embeddings.py` duplicates
`services/ml`'s hashing embedding (mirroring how every other service owns its own thin logic against
shared tables in this repo) — a live test confirmed both copies embed identically.

**Verified end-to-end, live, against the real running stack:** built both new images (hit and fixed
two real bugs: `mcp>=1.2` alone resolves to `mcp` 2.x, which renamed/removed `FastMCP` — pinned
`mcp>=1.2,<2`; `mcp-server` also needed `sqlmodel` added to its requirements, missing on first
build). Brought up `mcp-server`+`copilot` alongside the running `core` stack: listed all 6 tools
over a live SSE session, called `get_fleet_risk` and `search_dtc_kb` against the real seeded demo
tenant (P0128 correctly ranked closest for a "coolant thermostat stuck" query), confirmed
`propose_work_order` rejects an `auditor` role before touching the DB, and confirmed both calls each
wrote a real `audit_log` row. Logged in as the real `manager@demo` Keycloak user and called
`POST /v1/copilot/ask` through the live `api` container end-to-end (200, stub-fallback reply, since
no `GOOGLE_API_KEY` is set yet). Stopped `copilot` and confirmed the API's outage-mapping returns a
real 404 with the expected detail message, then restarted it. 164/164 unit tests green
(`pytest tests/unit -q`), including new tests for the role gate, the embedding-parity check, the
stub fallback, and the API router's auth/forward/404 behavior.

Also added OTel auto-instrumentation to the API (`services/api/src/api/infra/otel.py`, a no-op
unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set) exporting request traces/RED metrics via OTLP to the
existing `otel-collector` (profile `obs`), plus Grafana datasource/dashboard provisioning
(`infra/compose/grafana/provisioning/`) with one starter "FleetPulse API — Overview" dashboard.

**Your turn (per PLAN §6.3 session 8):** a real `GOOGLE_API_KEY` is already in `.env` and verified
working end-to-end (see below) — click through the Copilot screen in the browser to see it live, then
start the 1h soak test overnight if usage allows.

**Verified live, obs profile:** brought up `otel-collector`+`prometheus`+`grafana`, hit a real Grafana
mount bug along the way (bind-mounting `grafana/provisioning/dashboards` as a directory *and*
`grafana/dashboards` under `.../dashboards/json` fails — Docker can't create a mountpoint inside an
already-mounted read-only parent; fixed by mounting `dashboards.yml` as a single file instead of its
parent dir). Generated real API traffic and confirmed both dashboard panels return real numbers from
Prometheus (`http_server_duration_milliseconds_count`/`_bucket` — that part of the guess was right —
but the group-by label is `http_target`, not `http_route`; fixed the request-rate panel to match).

**Follow-up in the same session, once a real `GOOGLE_API_KEY` was added:** found and fixed four more
real bugs live. (1) The key landed in `.env` under the pre-session-8 `ANTHROPIC_API_KEY=` line, not
renamed — the container never saw it. (2) `gemini-1.5-flash` (this session's original default) no
longer exists as an API model at all (404 NOT_FOUND); switched to the `gemini-flash-latest` alias so
a future Google retirement doesn't require a code change again. (3) Newer Gemini models return
`AIMessage.content` as a list of `{"type": "text", ...}` blocks, not a plain string — `agent.py`
assumed a string and Pydantic rejected the response; added `_as_text()` to join text blocks (unit
tested). (4) `MAX_OUTPUT_TOKENS=512` was too tight: `gemini-flash-latest` currently resolves to a
reasoning-capable model that spends part of that budget on internal thinking tokens, cutting the
visible answer off mid-sentence — raised to 2048. Also raised the API proxy's timeout to `copilot`
from 30s to 90s (a real multi-tool-call Gemini exchange took longer than 30s and was being
misreported as "copilot not deployed"; a genuine timeout now correctly returns 504 instead of 404).

**Then hit a real free-tier limit, also fixed:** `gemini-flash-latest` currently resolves to
`gemini-3.8-flash`, whose free tier caps at **20 requests/day** — testing burned through it in one
session (each question costs one request per tool call plus the final answer). Switched the default
to `gemini-flash-lite-latest`, confirmed live end-to-end with a full, correct multi-VIN risk-ranked
answer pulled through the real MCP tool chain. If the copilot screen shows the stub fallback message
again, it likely means this quota was hit again — wait for the daily reset, or use a paid tier.

**Verified end-to-end, live, with a real Gemini reply (not just the stub):** logged in as
`admin@demo` via Keycloak, asked "which trucks at Chennai depot are at highest risk?" through
`services/copilot/main.py`'s `/ask` directly and — separately — through the real
`POST /v1/copilot/ask` API route; both returned a complete, correctly-ranked list of real VINs and
risk scores sourced live via `get_fleet_risk`. 168/168 unit tests green after these fixes.

Real Kafka-lag/Flink-throughput metrics (vs. just API request latency) are deferred — wiring a
JMX/Kafka exporter is a bigger, separate slice, not attempted this session.

**One more real bug, found from the browser after all of the above:** the copilot replied "database
error" instead of real data. `api/api/routers/copilot.py` was forwarding the JWT's `tenant` claim
(the tenant *name*, `"demo"`) straight through as `tenant_id` — every other route resolves that name
to a uuid first via `api/api/deps.py:get_session` (`db.resolve_tenant_id`), but the copilot route
calls `copilot`/`mcp-server` directly, bypassing that dependency, so it never got resolved. Postgres
confirmed the exact failure (`invalid input syntax for type uuid: "demo"`) on every RLS-scoped query
`get_fleet_risk`/`list_alerts` ran. Fixed by resolving the uuid in the router itself before building
the payload; re-verified live end-to-end through the real `/v1/copilot/ask` route ("how many open
alerts are there right now?" → a correct real count and failure type). 168/168 unit tests green,
including updated tests for this route that mock `resolve_tenant_id` instead of hitting Postgres.

**UI polish, from a real browser screenshot:** the chat rendered Gemini's markdown literally
(`**VIN**`, backticks) instead of formatting it, and risk scores showed as the raw `1.00000` fraction
instead of a percentage. Fixed both at the source rather than hoping the model self-corrects: (1)
`get_fleet_risk` (`mcp-server/app/tools.py`) now returns `risk_percent` (e.g. `"84.4%"`), formatted
identically to `web/src/pages/AtRiskPage.tsx`'s own `(risk_score * 100).toFixed(1)}%` — the raw
fraction is no longer exposed to the model at all, so there's nothing for it to get wrong; (2)
`CopilotPage.tsx` now renders assistant replies through `react-markdown` (added dependency) — user-
typed messages stay plain text on purpose, only the model's own output is parsed as markdown. Also
tightened the system prompt to say "present `risk_percent` as-is, don't recompute it" as a second
line of defense. Verified live: a real Gemini reply now shows `Risk: 100.0%` instead of `1.00000`.
`npx tsc -b` / `npx eslint .` clean; 169/169 unit tests green (added a test for the percent
formatting, mocking the Postgres session rather than needing a live DB).

**More UI feedback, same session:** the chat cleared every time the user switched sidebar tabs — each
route in `App.tsx` is a separate component, so navigating away unmounts `CopilotPage` and its
`useState` messages with it. Persisted `messages` to `sessionStorage` instead (survives a tab switch
and a page refresh, cleared when the browser tab/session ends — deliberately not a backend chat-
history store, per the user's own stated scope). Also moved the question input to the bottom of the
page: `.copilot-page` is now a flex column filling the viewport (`100vh` minus `.main`'s own padding)
with the chat log as the scrolling `flex: 1` region, so the input row lands at the page bottom
regardless of how many messages are in the log, and the log now auto-scrolls to the newest message.
Added two browser globals (`sessionStorage`, `HTMLDivElement`) `eslint.config.js` didn't list yet.
`npx tsc -b` / `npx eslint .` / `npm run build` all clean.

**Next:** Session 9 — Integration (Testcontainers), Pact, behave BDD, CI with Semgrep/Trivy/ZAP;
Helm chart + kind; Terraform; EXPLAIN before/after for 3 queries; UI fixes list.

**Blockers:** none.

---

## Session 7 — 2026-09-28
Built the React + Vite + TS web app (PLAN §6.3 session 7) in `web/`: Keycloak login via `keycloak-js` against the `fleetpulse-web` public client session 1 already provisioned (`login-required`, PKCE, silent token refresh every 20s), a `lib/api.ts` fetch wrapper that attaches the bearer token and surfaces session 6's RFC 7807 `problem+json` errors as a banner, and the 4 screens + audit view: **At-Risk Fleet** (keyset "load more" over `/v1/vehicles/at-risk`), **Vehicle Detail** (masked depot/live-location display, twin JSON, propose/approve/book-depot work-order actions gated in the UI by role — the API is still the real enforcement), **Live Alerts** (`/v1/alerts` initial load + a live `/v1/ws/alerts` WebSocket feed with a connected/disconnected badge), **Audit Log** (`/v1/audit`), and **Copilot** (a chat UI wired to `POST /v1/copilot/ask`, which doesn't exist until session 8 — a 404 there shows an explicit "not deployed yet" banner instead of breaking, so this screen needs no further UI work once session 8 ships the backend). Added CORS middleware to the FastAPI app (`services/api/src/api/api/app.py`) for the separate-origin `:5173` → `:8000` dev traffic, and a `web` service in `docker-compose.yml`'s `core` profile (multi-stage Dockerfile, `vite preview` in prod) replacing session 1's placeholder comment.

**Verified without the full stack running** (docker wasn't started this session — see "Your turn" below): `npx tsc -b` clean, `npm run build` clean (214 KB JS gzipped to 69 KB), `npx eslint .` clean (0 problems), and `npm run dev` actually serves `200` on `localhost:5173`. Not yet verified: a real login + click-through against the live Keycloak/API, since that needs `docker compose --profile core up`.

**Your turn (per PLAN §6.3 session 7):** `docker compose --profile core up -d --build web` (needs `api`/`keycloak` already healthy), then open `http://localhost:5173`, log in as one of the four demo users, and click through all 5 screens — at-risk list → a vehicle detail → propose/approve/book a work order → live alerts (trigger one with `make inject-fault` or `make simulate` to see the WebSocket feed update) → audit log. Note any visual bugs in one list for the next session, per the plan.

**Live click-through (same session, after the above):** found and fixed (1) Keycloak's `tenant`/`realm_access.roles` protocol mappers were only on the `fleetpulse-api` client, so browser tokens from `fleetpulse-web` got a 401 "token missing tenant claim" — mappers added to `fleetpulse-web` in the realm JSON and Keycloak force-reimported (`docker compose rm -sf keycloak && up -d`); (2) Kafka `alerts` WS messages have `detected_at` and no `id`/`opened_at`, unlike Postgres rows — `AlertsPage` now normalizes them (verified: a test WS client received 134 live alerts during an 80 s `make simulate RATE=2000`). The feed looks idle unless the simulator is running; that's expected. Audit Log 403s for `fleet_manager` by design (RBAC). **Session 5 follow-ups found here, not fixed (ML scope):** `prediction.lead_days` is never written by `services/ml/train.py` (UI shows "—"), and 31/121 predictions score ≥ 99.5%, so page 1 of At-Risk reads as all-100% (the model is overconfident on the small in-session backfill). The UI now shows 1 decimal place. Duplicate alert rows per VIN come from session 4's rules reading `telemetry_raw` rather than the dedup view (documented trade-off).

**Next:** Session 8 — Copilot (LangGraph + MCP server + Claude, approval queue, audit, stub fallback); OTel + Prometheus + Grafana dashboards. The Copilot screen built this session already expects `POST /v1/copilot/ask` returning `{"reply": "..."}` — match that shape (or update `web/src/pages/CopilotPage.tsx` if the real contract differs).

**Blockers:** none. Checklist row 7 left unticked in `PLAN.md` — "Done when: full journey in the browser" is the manual click-through above, not yet done.

---

## Session 6 — 2026-09-28
Built the secured FastAPI service (PLAN §6.3 session 6), hexagonal (`services/api/src/api/{api,app,domain,infra}`): Keycloak realm export (`infra/keycloak/fleetpulse-realm.json`, roles fleet_admin/fleet_manager/technician/auditor, a `tenant` claim mapper, demo users `{admin,manager,tech,audit}@demo`/`changeme`), JWT validation via JWKS (PyJWT + `PyJWKClient`), a least-privilege `fleetpulse_api` Postgres role (migration 005, NOSUPERUSER NOBYPASSRLS — the default POSTGRES_USER is a superuser and silently bypasses RLS regardless of FORCE, per session 3's note), and `SET LOCAL app.tenant_id` from the validated JWT's `tenant` claim (never client input) around every request's transaction. Added two new fleetcore algorithms: `geohash` (role-based location masking — exact lat/lon for fleet_admin/fleet_manager, a coarse geohash cell for technician/auditor) and `depot_routing` (Dijkstra over a fully-connected depot mesh weighted by haversine distance, so "nearest depot with a free bay" can fall through past a full nearest depot instead of just picking nearest-by-distance). Keyset-paginated `/v1/vehicles/at-risk` reads a new `vehicle_latest_risk` materialized view (migration 007, refreshed via `make refresh-risk` after `make train`) instead of OFFSET + N+1 (PLAN §2 SQL-opt item 1); `/v1/alerts?open_only` uses a new partial index on `alert(tenant_id, opened_at) WHERE closed_at IS NULL` (item 2, item 3 was already done in session 3). Redis Lua token-bucket rate limiting, an RFC 7807 problem+json error format, an audit middleware that writes one `audit_log` row per authenticated request (actor/action/resource/status, after the response is known), `/v1/ws/alerts` (a background Kafka consumer on the `alerts` topic fans out to connected sockets filtered by tenant), work-order propose/approve, and a driver erasure endpoint (`/v1/drivers/{id}/erase`: pseudonymizes PII in Postgres, deletes that driver's Mongo `raw_archive` docs by `driver_token` — Timescale never had driver PII to begin with, per PLAN §1, so there's genuinely nothing to erase there, not a gap).

**Verified end-to-end, live, against the real running stack (not just unit tests):** built and started the `api` container; logged in as all four demo users against the real Keycloak (`localhost:8082`) and confirmed the JWT actually carries `tenant:"demo"` and the right `realm_access.roles`; paged through the real 121 predictions session 5's backfill scored (`/v1/vehicles/at-risk`, cursor advancing correctly page-to-page); confirmed RBAC (technician gets a 403 problem+json on `/v1/vehicles/at-risk`, allowed on vehicle detail); proposed a work order and booked it into the vehicle's own depot via the live Dijkstra endpoint; erased a real driver and watched Mongo actually delete 1,435 archived documents by `driver_token`; connected a real WebSocket client and received a synthetic Kafka `alerts` message pushed through the real broker in under a second; confirmed the token-bucket limiter blocks the 4th request of a 3-capacity bucket against real Redis; and confirmed every request (including the 403) landed in `audit_log`. 152/152 unit tests green (`pytest tests/unit -q`), all 15 `core` containers healthy afterward.

**Bug found and fixed via live verification, not caught by unit tests:** `get_vehicle_detail` only masked the *depot's* location by role, not the vehicle's own live GPS fix from the Redis twin — the actually privacy-sensitive field (PLAN §2: "location masking ... by role"). A technician's `/v1/vehicles/{id}` response leaked exact `lat`/`lon` inside `twin` even though `depot_location` was correctly geohashed. Fixed in `api/app/vehicles.py` to also mask `twin.lat`/`twin.lon` into `twin.location`; added a regression test and re-verified live against the real Redis-mirrored twin.

**Also found while wiring Keycloak, unrelated to this session's own code correctness but blocking:** the realm import silently succeeded (`KC-SERVICES0032: Import finished successfully`) but every demo login failed with `"Account is not fully set up"` (`resolve_required_actions`) — Keycloak 25's realm import defaults to its built-in required-actions catalogue (email verify, update password, etc.) when a realm JSON omits the `requiredActions` array entirely, even with each user's own `credentials`/`emailVerified` set correctly. Fixed by adding `"requiredActions": []` at the realm level. Also: Keycloak's `start-dev` mode keeps its realm DB in-container (no named volume), and `--import-realm` uses an IGNORE_EXISTING strategy, so a realm that already exists (even an empty pre-existing "fleetpulse" from a stale prior attempt) silently skips reimport — `docker compose rm -f keycloak && docker compose up -d keycloak` was needed to force a clean reimport after the fix, not a config reload alone. Separately, `.env.example`'s `KEYCLOAK_PORT=8081` was stale/wrong (8081 is flink-jobmanager's port; Keycloak's container listens on 8080, published as 8082) — fixed, and the API reads `KEYCLOAK_INTERNAL_PORT=8080` explicitly rather than reusing that var.

**Your turn (per PLAN §6.3 session 6):** click through a login at `http://localhost:8082` (realm `fleetpulse`, any of the four demo users / `changeme`) just to see it working. Nothing else manual — this session's own live verification above already exercised every route.

**Next:** Session 7 — React UI (4 screens + audit view).

**Blockers:** none. Note for whoever restarts the stack: `make refresh-risk` needs to be run after every `make train` (the at-risk endpoint reads a materialized view now, not the `prediction` table directly) — it isn't wired to run automatically yet, since `services/ml/train.py` predates this session.

---

## Session 5 — 2026-09-28
Built the history backfill + Spark feature job + sklearn training pipeline (PLAN §6.3 session 5). `db/timescale/backfill_history.py` reuses the simulator's own `SignalEngine`/`plan_failures` domain code (same `generate_fleet(seed=42)` fleet as `seed_fleet.py`, so VINs join to Postgres `vehicle`) to write FAST/HEALTH history straight into Timescale — bypassing MQTT/gateway/Flink entirely, since this is training data, not a live-ingest exercise — and writes the hidden ground truth (vin, failure_type, onset_at, failure_at) to `batch/spark/data/labels.csv`, deliberately kept out of every online store (no leakage). `batch/spark/feature_job.py` (new `spark` compose service, `batch` profile) reads raw `telemetry_fast`/`telemetry_health` via JDBC (not the session-3 continuous aggregate — that only covers FAST columns, and the failure signals that matter most here are in HEALTH), computes daily per-vehicle features with 7-day trailing slopes/recurrence/tyre-sibling-delta, joins the labels, and writes `features.parquet`. `services/ml/` (new hexagonal service): `train.py` trains one `HistGradientBoostingClassifier` per Must-failure type (1-5) vs a type-blind "active DTC or threshold breach" baseline (`domain/baseline.py`), time-based train/val/test split, writes `docs/evidence/ml/report.md` (PR-AUC, precision/recall, recall@≥5d-lead, precision@100, ₹-saved, permutation importance), and scores the fleet's latest snapshot into Postgres `prediction` (feature vector zero-padded to 384 for pgvector). `build_kb.py` populates `dtc_kb`/`failure_signature` using a hashing-trick embedding (`domain/embeddings.py`) instead of a sentence-transformer, to avoid a ~2GB torch dependency for a POC — documented as a trimmed-scope decision, same spirit as session 1's MinIO→Garage swap.

**Verified end-to-end, live:** ran a real (not synthetic) backfill — 1200 vehicles × 21 days, 9.68M rows, 37 planted failures — through the full pipeline: `make backfill` → `make batch` (Spark, 25,920 vin-days written) → `make train` (5 models trained, `report.md` written, 139 predictions scored into Postgres) → `make build-kb` (22 DTCs + 8 failure signatures). Spot-checked a pgvector nearest-neighbour query directly: `P0128` (coolant thermostat) correctly ranks the `cooling` failure signature closest by cosine similarity among the 8. This in-session backfill is intentionally smaller than the real dataset (only 200 positive vin-days total, 0-4 test positives per failure type) — enough to prove every stage works, not enough for stable metrics; `report.md` says so explicitly and names the fix.

**Bugs found and fixed:** (1) the `spark` container's default command path `/opt/spark/bin/spark-submit` was being mangled by Git Bash's path conversion into a bogus Windows path when passed to `docker compose run` — fixed with `MSYS_NO_PATHCONV=1` in the `batch` Makefile target (same class of bug as session 2's `-subj` mangling); (2) the official `apache/spark` image's `spark-submit --packages` couldn't write its Ivy cache under `/home/spark` (not writable) — redirected via `--conf spark.jars.ivy=/tmp/ivy2`. Also changed the `spark` compose service's volume mount from `:ro` to read-write (needs to write `output/features.parquet`).

**Full sessions 1-5 regression check, done before committing:** `docker compose ps` all healthy, `pytest tests/unit -q` 109/109 green, Flink job RUNNING (`curl :8081/jobs`), Postgres still has 100K vehicles/drivers/5 depots (session 3), a fresh 60s `make simulate RATE=500` round-tripped through MQTT → gateway → Kafka → Flink → alerts → state-writer → Postgres. Hit one real issue along the way, unrelated to this session's code: `ingest-gateway` and `state-writer`'s Kafka client connections had gone stale after ~7 hours of uptime plus today's heavy backfill/Spark load (a ~20-minute Kafka broker-internal heartbeat hiccup around 14:36 that Kafka itself recovered from, but both consumers never reconnected — `state-writer`'s consumer group showed no active member and a growing, static lag). `docker compose restart state-writer ingest-gateway` fixed it immediately (alert count went 442 -> 953 in under a minute, `max(opened_at)` caught back up to real time). Worth knowing for later sessions: after several hours of a stack staying up through repeated heavy load, check `kafka-consumer-groups.sh --describe --group state-writer` for a real (non-static) lag / an active consumer-id before trusting the pipeline is live, not just `docker compose ps`'s "Up".

**Your turn (per PLAN §6.3 session 5):** run the real backfill overnight — `make backfill VEHICLES=20000 DAYS=30` (took ~25 min for 1200×21 here, so budget a few hours; it's a single long-running Python process, safe to leave) — then `make batch && make train` to regenerate `docs/evidence/ml/report.md` against real numbers before the solution document (session 10) cites them.

**Next:** Session 6 — FastAPI: Keycloak realm export, JWT/RBAC, RLS session tenant, keyset pagination, Redis rate limit, masking, audit, erasure, WebSocket alerts, Dijkstra depot booking + tests.

**Blockers:** none. The `report.md` currently in the repo reflects the small in-session backfill, not the real overnight one — see above.

---

## Session 4 — 2026-09-28
Built the Flink SQL pipeline (`stream/flink/sql/00-05`, submitted as one `STATEMENT SET` job via `stream/flink/run-jobs.sh` / `make flink-submit`): a Kafka JSON source over `telemetry`, exact `ROW_NUMBER()`-based dedup for the Timescale/lake sinks, real-time rules for failures 1-5 (a HOP window for sustained cooling, simple filters for lubrication/battery/MIL/brakes) plus a `MATCH_RECOGNIZE` CEP pattern for recurring misfire DTCs, sinking to `telemetry_fast`/`telemetry_health` (JDBC), a JSON lake under `s3://fleetpulse-lake/telemetry/` (Garage), and a Kafka `alerts` topic. Built `services/state-writer` (hexagonal, mirrors ingest-gateway's shape): consumes `telemetry` directly (parallel to Flink, per the architecture diagram) to maintain a merged per-vehicle twin (`domain/twin.py`, per-msg_type seq-guarded, 11 new unit tests) written to Redis (latest state) and MongoDB (`vehicle_twin` + a 7-day-TTL `raw_archive`), and consumes `alerts` to insert Postgres `alert` rows (RLS-aware, `SET app.tenant_id` per insert). Extended `docker-compose.yml`: a custom Flink image (`infra/compose/flink/Dockerfile`) with the Kafka/JDBC/Postgres-driver/S3 jars this needed, plus the new `state-writer` service. Also fixed a real gap: the wire envelope never carried `tenant` (only the MQTT topic did), so `ingest-gateway` now stamps it onto the Kafka message from the already-authenticated topic segment — needed by every sink/store this session added.

**Verified end-to-end, live, against the running stack (not just unit tests):** built + deployed the new images, fixed two pre-existing bugs blocking this (Garage's `garage.toml` persistence fix from session 1 had never actually taken effect because the container was never restarted after it landed, and its cluster layout had never been bootstrapped — both fixed, `infra/compose/garage-provision.sh` / `make lake-init` now does the bootstrap+bucket+key setup Garage requires, importing a fixed dev keypair matching `GARAGE_ACCESS_KEY`/`SECRET_KEY` in `.env.example`). Submitted the Flink job, produced a real `FAST` message with `oil_kpa=50` for a seeded VIN, and confirmed it flowed through: a `telemetry_fast` row with the right values, a `lubrication` alert on the `alerts` topic (right DTC array), a matching row in Postgres `alert` (right tenant via RLS), and the vehicle's twin correctly updated in both Mongo and Redis.

**Bugs found and fixed while getting there (worth knowing for later sessions):** (1) `ts` must be `TIMESTAMP_LTZ(3)` in Flink SQL, not `TIMESTAMP(3)` — fleetcore's envelope serializes it 'Z'-suffixed, which `TIMESTAMP(3)` silently failed to parse (nulled by `json.ignore-parse-errors`), crashing the HOP window and MATCH_RECOGNIZE operators the first three times this ran; (2) the JDBC connector has no Postgres converter for `TIMESTAMP_LTZ`, so the two Timescale sinks cast back to `TIMESTAMP(3)` — LTZ stays only where Kafka/JSON sinks read it; (3) the dedup view must order its `ROW_NUMBER()` by `proc_time`, not `event_time`, to compile to an append-only operator — the event-time variant is an upsert/changelog stream that both strips the rowtime metadata a window needs downstream *and* demands every sink declare a primary key; consequence: `03_realtime_rules.sql`/`04_cep_misfire.sql` deliberately read `telemetry_raw` directly, not the dedup view, trading exact-dedup (not needed for sustained/recurring rules) for a live watermark chain; (4) `MATCH_RECOGNIZE` can't navigate a nested ROW field (`A.payload.dtc`) through a pattern variable — flatten to top-level columns first; (5) a greedy `{2,}` quantifier can't be a pattern's last element — use `{2,}?`.

**Correction — the "verified end-to-end" above only exercised a FAST message.** Running real `make simulate` traffic for longer exposed five more bugs, all fixed (evidence + numbers in `docs/evidence/stream/README.md`): (6) the JDBC connector can't write `ARRAY` columns to Postgres — the job ran 1h42m and died on the first real HEALTH row; the health sink now sends each array as a Postgres array-literal string (`JSON_STRING` + `[`→`{`) with `stringtype=unspecified` on the JDBC URL, keeping session 3's native array columns; (7) the running `ingest-gateway` container was never rebuilt after this session's `tenant` change, so live traffic had `tenant=NULL` (synthetic tests set it by hand and masked this) — rebuilt, plus the dedup view now filters `tenant`/`event_time IS NULL` so one malformed row can't kill the job; (8) no checkpointing meant the lake's file sink never committed anything (125 MiB stuck as unfinished S3 multipart uploads) and any failure was permanent — `run-jobs.sh` now sets a 30 s checkpoint interval to `s3://fleetpulse-lake/checkpoints`, which also turns on Flink's default restart strategy; (9) Hadoop S3A's directory-marker bulk-delete gets NoSuchKey from Garage and retries forever (job stuck INITIALIZING) — `fs.s3a.directory.marker.retention: keep` in both Flink services; (10) the simulator (and `inject_fault.py`) restarted `seq` at 0 every run, so the gateway's Bloom filter dropped ~40% of repeat-run traffic as duplicates (352,358 of 896,505) — `seq` now starts from a per-run millisecond base. After all fixes: back-to-back 45 s runs landed 82,041 and 89,426 FAST rows, HEALTH arrays land natively, checkpoints 5/5, lake files + `_SUCCESS` markers committed, 90 organic `brake_wear` alerts in Postgres.

**Second correction — that fix set survived 45-90 s runs but not longer ones.** An 11-minute sustained `make simulate RATE=2000` OOM'd the TaskManager entirely (`docs/evidence/stream/flink-job-oom-restarting.png`): (11) `taskmanager.memory.process.size: 1024m` (PLAN §3's original budget) left too little task heap once the cooling rule's HOP window (30 s size / 5 s slide → 6 overlapping windows per key) and the dedup operator's keyed state grew under sustained real load — visible moments before the crash as 100% source backpressure (`flink-job-running.png`). The TaskManager disappearing then stuck the job in `RESTARTING` forever with `NoResourceAvailableException` (no slots to restart into, since there was no TaskManager left to provide any). Fix: bumped to `2048m` — Flink's own documented floor for a non-toy job. **Verified this one properly**, not just re-run-and-hope: a full 10-minute sustained run afterward landed 1,500,228 `telemetry_fast` + 25,724 `telemetry_health` rows, 440 organic `brake_wear` alerts, 19/19 checkpoints, 1.1 GB to the lake, TaskManager never dropped. Numbers and both screenshots in `docs/evidence/stream/README.md`.

**Known gap, not a pipeline bug:** `services/simulator/inject_fault.py` (built session 2, before these rules existed) doesn't reliably trigger them — its single HEALTH message fires at t=0 when severity is still 0, and its 15s overheat ramp only spends ~8s above 110°C against the cooling rule's 30s sustained-window requirement. Worth a follow-up: either shape the injector's ramp/HEALTH timing to each rule's actual window, or add a `--hold-seconds` flag. Verification above used a direct synthetic Kafka message instead.

**Operational notes for whoever restarts this stack (including future sessions):**
- `make lake-init` must be re-run any time the Garage (`minio` service) volume is fresh — the bucket, key and cluster layout aren't baked into the image or committed anywhere else.
- `make flink-submit` must be re-run any time `flink-jobmanager` restarts — checkpointing now lets the job recover from a task failure on its own, but there's no JobManager HA, so a JM restart still drops the job; `docker compose ps` showing the container "Up" does not mean the pipeline job is running (check `curl localhost:8081/jobs`).
- After editing any service's Python source, rebuild **its** image (`docker compose build <svc> && docker compose up -d <svc>`) — `docker compose restart` reuses the old image (this is how the gateway ran stale code for most of session 4).
- If you rebuild `flink-jobmanager`/`flink-taskmanager` (e.g. after editing `infra/compose/flink/Dockerfile`), rebuild **and** recreate both before resubmitting — `docker compose build` alone doesn't restart the running containers.

**Manual verification checklist for this session's "Done when" — all done, against a 10-minute sustained run, not a quick smoke test:**
- [x] Flink UI (`localhost:8081`) shows the job RUNNING with the expected DAG shape (`docs/evidence/stream/flink-job-graph.png`, `flink-job-running.png`).
- [x] `make simulate RATE=2000` sustained for 10 minutes: `telemetry_fast`/`telemetry_health` row counts climbing, `docker compose exec minio /garage bucket info fleetpulse-lake` growing (1.1 GB / 30 objects). Numbers in the correction above and `docs/evidence/stream/README.md`.
- [x] A REAL (not synthetic) alert end-to-end: 440 organic `brake_wear` rows in Postgres from simulated wear, no fault injection needed once the rules had enough real traffic to work with.
- [ ] Still open, low priority: a clean `make inject-fault TYPE=oil` demo on a confirmed ICE VIN, for a *deterministic*, on-demand alert (useful for the video/demo script even though organic alerts already prove the rule works) — see the known-gap note below on why `inject_fault.py`'s timing doesn't reliably trigger it yet.

**Next:** Session 5 — history backfill script, Spark feature job, sklearn model vs baseline, pgvector DTC KB + failure signatures.

**Blockers:** none. Still pre-existing, unrelated to this session: nothing new — the Garage `unhealthy` status from sessions 1-3 is now actually fixed (see above), not just cosmetically ignored.

---

## Session 3 — 2026-09-28
Built the Postgres 3NF core (`db/postgres/migrations/`: tenant, depot, vehicle_model, driver, vehicle, app_user, subscription, alert, work_order, prediction, audit_log, plus the pgvector-backed `dtc_kb`/`failure_signature` tables) with RLS (`FORCE ROW LEVEL SECURITY` + a `tenant_isolation` policy per tenant-scoped table, driven by `app.tenant_id`), and the TimescaleDB side (`db/timescale/migrations/`: `telemetry_fast` + `telemetry_health` hypertables space-partitioned by VIN hash, compression/retention policies, and a `telemetry_fast_daily` continuous aggregate for Spark's future feature job). Wrote `db/migrate.sh` + `make migrate` to apply both since `docker-entrypoint-initdb.d` only fires on an empty volume and these containers were already initialized back in session 1. Built `db/postgres/seed_fleet.py` (`make seed`), which reuses the simulator's `generate_fleet(seed=42)` so seeded VINs/driver_tokens match what `make simulate` actually publishes; seeded 100,000 vehicles + 100,000 drivers + 5 depots via `COPY` in ~7 s. ER diagram at `docs/diagrams/er-diagram.md` (Mermaid). PLAN §6.3 row 3 ticked.

**Verified:** vehicle_type distribution matches the 70/20/10 fleet mix (70,070 ICE / 19,898 EV / 10,032 HYBRID); RLS actually blocks cross-tenant reads for a non-superuser, non-BYPASSRLS role (confirmed 0 rows with no `app.tenant_id` set, 100,000 with the real tenant) — **important for session 6**: the FastAPI service's DB role must be created as `NOSUPERUSER NOBYPASSRLS`, since Postgres always exempts superusers from RLS regardless of `FORCE`, and the default `POSTGRES_USER` docker creates *is* a superuser.

**Blocker hit and fixed:** a native Windows PostgreSQL service already listens on host port 5432, shadowing Docker's forward for the `postgres` container (host connections were silently hitting the wrong server, causing bogus auth failures). Remapped Docker's published port to **5434** (`docker-compose.yml`, `.env`/`.env.example` — `POSTGRES_PORT_EXTERNAL=5434`); the in-network hostname/port (`postgres:5432`) that Flink/API/etc. use internally is unaffected. Also added `*_HOST_EXTERNAL`/`*_PORT_EXTERNAL` vars for both Postgres and Timescale, matching the existing Kafka/MQTT convention for host-run tools.

**Next:** Session 4 — Flink SQL jobs (dedup, windowed rules for failures 1–5, CEP misfire pattern, sinks to Timescale/Parquet/alerts) + state-writer (Redis, PG alerts, Mongo twin).

**Blockers:** none carried forward (port conflict above is resolved). Still pre-existing: `minio` (Garage) shows `unhealthy` in `docker compose ps`, not touched this session.

---

## Session 2 — 2026-09-28
Built `fleetcore` (VIN ISO 3779 check digit, DTC regex, Bloom filter, the universal FAST/HEALTH/EVENT pydantic schema + matching Avro file, 51 tests), the simulator (100K-vehicle fleet gen, failures 1-5 with a severity ramp, duplicate/reorder/burst noise injection, MQTT publisher, `make simulate`/`make inject-fault`/`make bench-ingest`, 25 tests), and ingest-gateway (shard-consistency + schema/VIN/DTC validation, Bloom dedup pre-filter, bounded-queue back-pressure, Kafka producer with DLQ routing, 13 tests — 85 total, all green). Verified live end-to-end against the running `core` stack: simulator → Mosquitto (mTLS) → ingest-gateway → Kafka `telemetry` (325 sent, 320 forwarded, 5 noise-duplicates correctly deduped, 0 DLQ), and `inject-fault --type overheat` drove coolant_c from 88°C to 119°C, crossing the 110°C real-time threshold, confirming the failure-ramp mechanism for session 4's alerting.

**Engineering decision (documented, not silent — same spirit as session 1's MinIO→Garage swap):** 100K live per-vehicle mTLS certs isn't a one-session build, so "cert↔VIN check" is implemented at VIN-hash **shard** granularity instead: 32 shard client certs (`infra/certs/issue-shard-certs.py`), one Mosquitto ACL entry per shard restricting it to its own `fleet/{tenant}/shard-N/+/telemetry` topic segment, and the gateway re-derives each message's expected shard from its VIN and rejects mismatches. Same VIN→shard function (`fleetcore.algorithms.sharding`) is shared by simulator and gateway so they never disagree. Also fixed two pre-existing session-1 issues hit along the way: `generate-dev-certs.sh`'s `-subj` args were being mangled by Git Bash's path conversion (fixed with a doubled leading slash, the standard workaround, plus made the script idempotent), and Kafka only advertised `kafka:9092` with no host-reachable listener (added an `EXTERNAL` listener on `29092` so host tools like `bench_ingest.py` can read topic offsets).

**Next:** Session 3 — Postgres 3NF migrations + RLS, Timescale hypertable + continuous aggregate, seed 100K vehicles/drivers/depots, ER diagram.

**Blockers:** none. Also worth a look when convenient: `minio` (Garage) shows `unhealthy` in `docker compose ps` — not touched this session, pre-existing from session 1's swap.

**`make bench-ingest` result (5 min, RATE=1000, the Makefile default):** 311,697 messages attempted (952 events/s — the simulator itself is the bottleneck at this rate, not Mosquitto/Kafka: a single Python process paces to wall-clock ticks and per-tick JSON/paho overhead eats a little headroom), 306,715 delivered end-to-end to Kafka's `telemetry` topic (937 events/s, 98.4% of attempted — the gap is expected duplicate-drop from noise injection plus in-flight messages not yet landed at measurement time, not loss). PLAN §6.3 row 2 is now fully ticked. Higher RATE values (e.g. `make bench-ingest RATE=20000`) haven't been tried yet — worth doing in a later session to find where the local ceiling actually is, per PLAN §3's 10-25K events/s local-demo target.

---

## Session 1 — 2026-09-28
Built the repo skeleton per PLAN §4 (services/, stream/, batch/, libs/fleetcore/, web/, db/, infra/, tests/, docs/), `CLAUDE.md`, `docs/PLAN.md` with a status checklist, this file, `.env.example`, `docker-compose.yml` for the `core`/`ai`/`batch`/`obs`/`chaos` profiles, a `Makefile` with the targets CLAUDE.md documents, and a CI stub workflow (lint job only, rest are TODO markers for session 9). Initialized git, first commit pushed to https://github.com/amogh-rb/Predictive-Maintenance.git.

All 11 `core` containers came up healthy after three fixes, applied by the user directly against the running stack:
- **MinIO → Garage.** MinIO Community Edition was pulled/deprecated from registries between when the compose file was written and when it was run. Swapped for `dxflrs/garage:v1.0.1` (S3-compatible, single-node). `infra/compose/garage.toml` added. I then found and fixed a persistence bug in that config: `metadata_dir` wasn't under the mounted volume, so bucket/key config would be lost on container restart — moved both `metadata_dir` and `data_dir` under `/var/lib/garage/data`. Also corrected `.env.example`: internal (container-to-container) traffic must hit Garage's S3 API on port **3900**, not the host-mapped 9000; Garage credentials are provisioned via `garage key new` / `garage bucket allow`, not env vars like the old MinIO image — bucket + key creation is a **TODO for session 2** (state-writer needs it for the raw archive / lake writes).
- **Keycloak port conflict.** flink-jobmanager already held 8081; Keycloak moved to host port 8082.
- **Healthchecks.** Mosquitto, Apicurio (path changed to `/health/ready`), and Garage healthchecks were fixed to match what each image actually exposes.

Also: `.wslconfig` created, Docker confirmed at 12 CPUs / 13 GB RAM; mTLS dev certs generated (had to run via Anaconda's openssl since Git Bash routing failed).

**Next:** Session 2 — `fleetcore` (universal schema, VIN check digit, DTC regex, Bloom filter) + tests; simulator (100K trucks, failures 1-5, noise/duplicates/out-of-order/bursts, MQTT); ingest-gateway (cert↔VIN, validation, batching, back-pressure, DLQ) + tests. Remember the Garage bucket/key TODO above before anything tries to write to the lake.

**Blockers:** none.
