import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { currentRoles } from "../lib/keycloak";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import SkeletonRows from "../components/SkeletonRows";
import { StatCard, StatGrid } from "../components/StatCard";
import { ClockIcon, TruckIcon, WrenchIcon } from "../components/icons";
import type { ScheduledItem, ScheduledList } from "../types";

function fmt(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function MaintenancePage() {
  const [items, setItems] = useState<ScheduledItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const canComplete = currentRoles().some((r) => ["fleet_admin", "fleet_manager", "technician"].includes(r));

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<ScheduledList>("/v1/maintenance/scheduled?limit=200");
      setItems(res.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function markServiced(item: ScheduledItem) {
    setBusy(item.work_order_id);
    setError(null);
    try {
      await api.post(`/v1/maintenance/${item.work_order_id}/complete`);
      setItems((prev) => prev.filter((i) => i.work_order_id !== item.work_order_id));
      setMessage(`${item.vin} marked serviced — the depot bay is free again.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(null);
    }
  }

  const depots = new Set(items.map((i) => i.depot_city)).size;

  return (
    <div>
      <PageHeader
        icon={<WrenchIcon />}
        title="Maintenance Scheduled"
        subtitle="Vehicles booked into their nearest depot from the At-Risk Fleet tab, until they are marked serviced."
      />

      {!loading && items.length > 0 && (
        <StatGrid>
          <StatCard label="Scheduled" value={items.length} icon={<WrenchIcon width={15} height={15} />} tone="accent" />
          <StatCard label="Depots in use" value={depots} icon={<TruckIcon width={15} height={15} />} tone="ok" />
          <StatCard
            label="Latest booking"
            value={fmt(items[0].booked_from)}
            sub="most recent depot slot"
            icon={<ClockIcon width={15} height={15} />}
            tone="warn"
          />
        </StatGrid>
      )}

      {error && <p className="problem-banner">{error}</p>}
      {message && <p className="info-banner">{message}</p>}

      <div className="table-card">
        <table>
          <thead>
            <tr>
              <th>VIN</th>
              <th>Failure type</th>
              <th>Risk when booked</th>
              <th>Depot</th>
              <th>Booked</th>
              <th>Bay held until</th>
              {canComplete && <th></th>}
            </tr>
          </thead>
          <tbody>
            {loading && items.length === 0 && <SkeletonRows columns={canComplete ? 7 : 6} />}
            {items.map((item) => (
              <tr key={item.booking_id}>
                <td>
                  <Link to={`/vehicles/${item.vehicle_id}`}>{item.vin}</Link>
                </td>
                <td>{item.failure_type ?? "—"}</td>
                <td>{item.risk_score !== null ? `${(item.risk_score * 100).toFixed(1)}%` : "—"}</td>
                <td>{item.depot_city}</td>
                <td>{fmt(item.booked_from)}</td>
                <td>{fmt(item.booked_until)}</td>
                {canComplete && (
                  <td>
                    <button
                      className="secondary"
                      disabled={busy === item.work_order_id}
                      onClick={() => markServiced(item)}
                    >
                      {busy === item.work_order_id ? "Saving…" : "Mark serviced"}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && items.length === 0 && !error && (
          <EmptyState
            icon={<WrenchIcon width={32} height={32} />}
            title="Nothing scheduled"
            detail="Book a vehicle from the At-Risk Fleet tab and it will appear here."
          />
        )}
      </div>
    </div>
  );
}
