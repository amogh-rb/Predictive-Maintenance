export interface AtRiskItem {
  vehicle_id: string;
  vin: string;
  failure_type: string;
  risk_score: number;
  lead_days: number | null;
  depot_name: string;
  depot_city: string;
}

export interface AtRiskPage {
  items: AtRiskItem[];
  next_cursor: string | null;
}

export interface MaskedLocation {
  lat?: number;
  lon?: number;
  geohash?: string;
}

export interface VehicleTwin {
  [key: string]: unknown;
  location?: MaskedLocation;
}

export interface VehicleDetail {
  id: string;
  vin: string;
  status: string;
  fw_version: string;
  make: string;
  model: string;
  vehicle_type: string;
  depot_id: string;
  depot_name: string;
  depot_city: string;
  depot_location: MaskedLocation;
  driver_name: string | null;
  twin: VehicleTwin | null;
}

export interface Alert {
  id: string;
  vehicle_id: string;
  vin: string;
  failure_type: string;
  severity: string;
  source: string;
  dtc_codes: string[];
  opened_at: string;
  closed_at: string | null;
}

export interface AuditLogEntry {
  id: string;
  actor: string;
  action: string;
  resource: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface ScheduledItem {
  booking_id: string;
  work_order_id: string;
  vehicle_id: string;
  vin: string;
  failure_type: string | null;
  risk_score: number | null;
  lead_days: number | null;
  depot_name: string;
  depot_city: string;
  booked_from: string;
  booked_until: string;
}

export interface ScheduledList {
  items: ScheduledItem[];
}

export interface ScheduleResult {
  work_order_id: string;
  booking_id: string;
  depot_id: string;
  depot_name: string;
  depot_city: string;
  hours: number;
}
