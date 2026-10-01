import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { currentRoles } from "../lib/keycloak";
import PageHeader from "../components/PageHeader";
import { MapPinIcon, TruckIcon, WrenchIcon } from "../components/icons";
import type { ScheduleResult, VehicleDetail } from "../types";

function statusBadgeClass(status: string): string {
  const s = status.toLowerCase();
  if (s === "active") return "badge sev-low";
  if (s === "maintenance") return "badge sev-medium";
  return "badge sev-high";
}

function locationText(loc: VehicleDetail["depot_location"] | undefined) {
  if (!loc) return "unknown";
  if (loc.lat !== undefined && loc.lon !== undefined) return `${loc.lat.toFixed(4)}, ${loc.lon.toFixed(4)}`;
  if (loc.geohash) return `~${loc.geohash} (masked for your role)`;
  return "unknown";
}

export default function VehicleDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [vehicle, setVehicle] = useState<VehicleDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canSchedule = currentRoles().some((r) => ["fleet_admin", "fleet_manager"].includes(r));

  async function load() {
    if (!id) return;
    try {
      setVehicle(await api.get<VehicleDetail>(`/v1/vehicles/${id}`));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function schedule() {
    if (!id) return;
    setBusy(true);
    try {
      const res = await api.post<ScheduleResult>(`/v1/maintenance/schedule/${id}`);
      setActionMsg(`Booked at ${res.depot_city} depot — see Maintenance.`);
    } catch (err) {
      setActionMsg(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (error) return <p className="problem-banner">{error}</p>;
  if (!vehicle) return <p className="muted">Loading…</p>;

  return (
    <div>
      <PageHeader
        icon={<TruckIcon />}
        title={vehicle.vin}
        subtitle={
          <span>
            {vehicle.make} {vehicle.model} · {vehicle.vehicle_type}{" "}
            <span className={statusBadgeClass(vehicle.status)}>{vehicle.status}</span>
          </span>
        }
      />

      <div className="card">
        <dl className="kv">
          <dt>Firmware</dt>
          <dd>{vehicle.fw_version}</dd>
          <dt>Driver</dt>
          <dd>{vehicle.driver_name ?? "unassigned"}</dd>
          <dt>Depot</dt>
          <dd>
            {/* depot_name is just a lowercase slug of the city in the seed
                data ("chennai") and depot_city is the display-cased form
                ("Chennai") — one depot per city, so both together read as
                "chennai (Chennai)". */}
            {vehicle.depot_city} — {locationText(vehicle.depot_location)}
          </dd>
          <dt>Live location</dt>
          <dd>{locationText(vehicle.twin?.location)}</dd>
        </dl>
      </div>

      <div className="card">
        <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <MapPinIcon width={15} height={15} /> Live twin
        </h3>
        {vehicle.twin ? (
          <pre className="mono" style={{ whiteSpace: "pre-wrap", fontSize: 13, margin: 0 }}>
            {JSON.stringify(
              Object.fromEntries(Object.entries(vehicle.twin).filter(([k]) => k !== "location")),
              null,
              2,
            )}
          </pre>
        ) : (
          <p className="muted">No live twin yet (vehicle has not reported).</p>
        )}
      </div>

      <div className="card">
        <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <WrenchIcon width={15} height={15} /> Maintenance
        </h3>
        <div className="toolbar">
          <button disabled={!canSchedule || busy} onClick={schedule}>
            {busy ? "Booking…" : "Schedule service"}
          </button>
        </div>
        {actionMsg && <p className="muted">{actionMsg}</p>}
      </div>
    </div>
  );
}
