-- "Maintenance scheduled": a vehicle booked into a depot from the at-risk tab leaves that list and
-- shows in its own tab until the work order is marked serviced.
--   scheduled = depot_booking whose work_order is still 'approved'
--   at-risk   = vehicle_latest_risk minus vehicles booked since their last scoring (repositories.py)
ALTER TABLE work_order ADD COLUMN IF NOT EXISTS completed_at timestamptz;

-- Both lookups go by vehicle, newest booking first; the existing index is by depot.
CREATE INDEX IF NOT EXISTS idx_depot_booking_vehicle ON depot_booking (vehicle_id, created_at DESC);
