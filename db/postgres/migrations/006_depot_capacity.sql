-- Depot service-bay capacity, for the copilot's/API's
-- `find_nearest_depot`/work-order-booking flow (PLAN §2 algorithms:
-- "Dijkstra/A* to the nearest depot with a free slot").
ALTER TABLE depot ADD COLUMN IF NOT EXISTS bays smallint NOT NULL DEFAULT 4;

CREATE TABLE IF NOT EXISTS depot_booking (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenant(id),
    depot_id        uuid NOT NULL REFERENCES depot(id),
    vehicle_id      uuid NOT NULL REFERENCES vehicle(id),
    work_order_id   uuid REFERENCES work_order(id),
    booked_from     timestamptz NOT NULL DEFAULT now(),
    booked_until    timestamptz NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Not a partial index on `booked_until > now()`: partial-index predicates
-- must be IMMUTABLE and now() is only STABLE. The API's free-bay count
-- filters on booked_until at query time using this composite index instead.
CREATE INDEX IF NOT EXISTS idx_depot_booking_depot_until
    ON depot_booking (depot_id, booked_until);

ALTER TABLE depot_booking ENABLE ROW LEVEL SECURITY;
ALTER TABLE depot_booking FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON depot_booking;
CREATE POLICY tenant_isolation ON depot_booking
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

GRANT INSERT, UPDATE ON depot_booking TO fleetpulse_api;
