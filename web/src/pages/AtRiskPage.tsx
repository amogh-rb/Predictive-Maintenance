import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { currentRoles } from "../lib/keycloak";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import SkeletonRows from "../components/SkeletonRows";
import { StatCard, StatGrid } from "../components/StatCard";
import { AlertIcon, ClockIcon, GaugeIcon, TruckIcon } from "../components/icons";
import type { AtRiskItem, AtRiskPage as AtRiskPageData, ScheduleResult } from "../types";

function riskTone(score: number): "risk-high" | "risk-medium" | "risk-low" {
  if (score >= 0.7) return "risk-high";
  if (score >= 0.4) return "risk-medium";
  return "risk-low";
}

export default function AtRiskPage() {
  const [items, setItems] = useState<AtRiskItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const canSchedule = currentRoles().some((r) => ["fleet_admin", "fleet_manager"].includes(r));

  async function loadPage(cursorParam: string | null, append: boolean) {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ limit: "20" });
      if (cursorParam) qs.set("cursor", cursorParam);
      const page = await api.get<AtRiskPageData>(`/v1/vehicles/at-risk?${qs}`);
      setItems((prev) => (append ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function schedule(item: AtRiskItem) {
    setBusy(item.vehicle_id);
    setError(null);
    try {
      const res = await api.post<ScheduleResult>(`/v1/maintenance/schedule/${item.vehicle_id}`);
      setItems((prev) => prev.filter((i) => i.vehicle_id !== item.vehicle_id));
      setMessage(`${item.vin} booked at ${res.depot_city} depot — moved to Maintenance.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    loadPage(null, false);
  }, []);

  const stats = useMemo(() => {
    const critical = items.filter((i) => i.risk_score >= 0.7).length;
    const leadDays = items.map((i) => i.lead_days).filter((d): d is number => d !== null);
    const avgLead = leadDays.length ? leadDays.reduce((a, b) => a + b, 0) / leadDays.length : null;
    const counts = new Map<string, number>();
    for (const i of items) counts.set(i.failure_type, (counts.get(i.failure_type) ?? 0) + 1);
    const top = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
    return { total: items.length, critical, avgLead, top };
  }, [items]);

  return (
    <div>
      <PageHeader
        icon={<TruckIcon />}
        title="At-Risk Fleet"
        subtitle="Vehicles predicted to fail soon, ranked by risk. Schedule service to book the nearest depot."
      />

      {!loading && items.length > 0 && (
        <StatGrid>
          <StatCard label="On this page" value={stats.total} icon={<TruckIcon width={15} height={15} />} tone="accent" />
          <StatCard
            label="Critical (≥70%)"
            value={stats.critical}
            icon={<AlertIcon width={15} height={15} />}
            tone="danger"
          />
          <StatCard
            label="Avg. lead time"
            value={stats.avgLead !== null ? `${stats.avgLead.toFixed(1)}d` : "—"}
            sub="days until predicted failure"
            icon={<ClockIcon width={15} height={15} />}
            tone="warn"
          />
          <StatCard
            label="Top failure type"
            value={stats.top ? stats.top[0] : "—"}
            sub={stats.top ? `${stats.top[1]} vehicle${stats.top[1] === 1 ? "" : "s"}` : undefined}
            icon={<GaugeIcon width={15} height={15} />}
            tone="ok"
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
              <th>Risk</th>
              <th>Lead days</th>
              <th>Depot</th>
              {canSchedule && <th></th>}
            </tr>
          </thead>
          <tbody>
            {loading && items.length === 0 && <SkeletonRows columns={canSchedule ? 6 : 5} />}
            {items.map((item) => (
              <tr key={`${item.vehicle_id}-${item.failure_type}`}>
                <td>
                  <Link to={`/vehicles/${item.vehicle_id}`}>{item.vin}</Link>
                </td>
                <td>{item.failure_type}</td>
                <td>
                  <span className="risk-track">
                    <span
                      className={`risk-bar ${riskTone(item.risk_score)}`}
                      style={{ width: `${Math.min(100, item.risk_score * 100)}%` }}
                    />
                  </span>
                  <span className="risk-pct">{(item.risk_score * 100).toFixed(1)}%</span>
                </td>
                <td>{item.lead_days ?? "—"}</td>
                {/* depot_name is just a lowercase slug of the city in the
                    seed data ("chennai") and depot_city is the display-cased
                    form ("Chennai") — there's one depot per city, so showing
                    both read as "chennai (Chennai)". The city alone is the
                    human-facing depot identity here. */}
                <td>{item.depot_city}</td>
                {canSchedule && (
                  <td>
                    <button disabled={busy === item.vehicle_id} onClick={() => schedule(item)}>
                      {busy === item.vehicle_id ? "Booking…" : "Schedule service"}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && items.length === 0 && !error && (
          <EmptyState
            icon={<TruckIcon width={32} height={32} />}
            title="No vehicles are at risk right now"
            detail="Predictions are refreshed regularly. Check back after the next scoring run."
          />
        )}
      </div>

      {cursor && (
        <button className="secondary" onClick={() => loadPage(cursor, true)} disabled={loading} style={{ marginTop: 16 }}>
          {loading ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}
