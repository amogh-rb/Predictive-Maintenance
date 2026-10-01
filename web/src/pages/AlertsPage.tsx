import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, wsUrl } from "../lib/api";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import SkeletonRows from "../components/SkeletonRows";
import { StatCard, StatGrid } from "../components/StatCard";
import { AlertIcon, ClockIcon, InboxIcon } from "../components/icons";
import type { Alert } from "../types";

function severityClass(sev: string) {
  return `badge sev-${sev.toLowerCase()}`;
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [openOnly, setOpenOnly] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  async function load() {
    setLoading(true);
    try {
      const rows = await api.get<Alert[]>(`/v1/alerts?open_only=${openOnly}&limit=50`);
      setAlerts(rows);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openOnly]);

  useEffect(() => {
    const ws = new WebSocket(wsUrl("/v1/ws/alerts"));
    wsRef.current = ws;
    ws.onopen = () => setLive(true);
    ws.onclose = () => setLive(false);
    ws.onerror = () => setLive(false);
    ws.onmessage = (evt) => {
      try {
        // Kafka `alerts` messages (Flink's sink) aren't Postgres rows: no id /
        // vehicle_id / opened_at yet, just `detected_at`.
        const msg = JSON.parse(evt.data) as Omit<Alert, "id" | "opened_at" | "closed_at"> & { detected_at: string };
        const alert: Alert = {
          ...msg,
          id: `live-${msg.vin}-${msg.detected_at}-${Math.random().toString(36).slice(2, 8)}`,
          opened_at: msg.detected_at,
          closed_at: null,
          dtc_codes: msg.dtc_codes ?? [],
        };
        setAlerts((prev) => [alert, ...prev].slice(0, 200));
      } catch {
        // non-JSON frame, ignore
      }
    };
    return () => ws.close();
  }, []);

  const stats = useMemo(() => {
    const critical = alerts.filter((a) => a.severity.toLowerCase() === "critical").length;
    const high = alerts.filter((a) => a.severity.toLowerCase() === "high").length;
    const latest = alerts[0];
    return { total: alerts.length, critical, high, latest };
  }, [alerts]);

  return (
    <div>
      <PageHeader
        icon={<AlertIcon />}
        title="Live Alerts"
        subtitle="Faults detected as trucks report them. New alerts appear here instantly."
      />

      <StatGrid>
        <StatCard label="Showing" value={stats.total} icon={<InboxIcon width={15} height={15} />} tone="accent" />
        <StatCard label="Critical" value={stats.critical} icon={<AlertIcon width={15} height={15} />} tone="danger" />
        <StatCard label="High" value={stats.high} icon={<AlertIcon width={15} height={15} />} tone="warn" />
        <StatCard
          label="Feed"
          value={
            <span style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 15 }}>
              <span className={`live-dot ${live ? "" : "off"}`} />
              {live ? "Live" : "Disconnected"}
            </span>
          }
          sub={stats.latest ? `last: ${new Date(stats.latest.opened_at).toLocaleTimeString()}` : undefined}
          icon={<ClockIcon width={15} height={15} />}
          tone={live ? "ok" : "warn"}
        />
      </StatGrid>

      <div className="toolbar">
        <label>
          <input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> Open only
        </label>
      </div>
      {error && <p className="problem-banner">{error}</p>}
      <div className="table-card">
        <table>
          <thead>
            <tr>
              <th>VIN</th>
              <th>Failure</th>
              <th>Severity</th>
              <th>Source</th>
              <th>DTCs</th>
              <th>Opened</th>
              <th>Closed</th>
            </tr>
          </thead>
          <tbody>
            {loading && alerts.length === 0 && <SkeletonRows columns={7} />}
            {alerts.map((a) => (
              <tr key={a.id}>
                <td>{a.vin}</td>
                <td>{a.failure_type}</td>
                <td>
                  <span className={severityClass(a.severity)}>{a.severity}</span>
                </td>
                <td>{a.source}</td>
                <td className="mono">{a.dtc_codes.join(", ")}</td>
                <td>{new Date(a.opened_at).toLocaleString()}</td>
                <td>{a.closed_at ? new Date(a.closed_at).toLocaleString() : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && alerts.length === 0 && !error && (
          <EmptyState
            icon={<InboxIcon width={32} height={32} />}
            title="No alerts"
            detail='New alerts appear here as soon as a truck reports a fault. Untick "Open only" to see past alerts.'
          />
        )}
      </div>
    </div>
  );
}
