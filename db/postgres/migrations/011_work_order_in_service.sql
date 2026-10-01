-- Maintenance status board: a booked vehicle can now be "in service" (at the depot, being worked on)
-- before it is completed, and a copilot proposal can be rejected.
--   proposed -> approved (booked into a depot) -> in_service -> completed ; proposed -> rejected
ALTER TYPE work_order_status ADD VALUE IF NOT EXISTS 'in_service';
ALTER TABLE work_order ADD COLUMN IF NOT EXISTS started_at timestamptz;
ALTER TABLE work_order ADD COLUMN IF NOT EXISTS rejected_at timestamptz;
