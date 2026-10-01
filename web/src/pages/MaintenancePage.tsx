import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { currentRoles } from "../lib/keycloak";
import PageHeader from "../components/PageHeader";
import { StatCard, StatGrid } from "../components/StatCard";
import { ClockIcon, TruckIcon, WrenchIcon } from "../components/icons";
import type { MaintenanceBoard } from "../types";

function fmt(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—";
}

function risk(score: number | null): string {
  return score !== null ? `${(score * 100).toFixed(1)}%` : "—";
}

function Column({
  title,
  hint,
  count,
  tone,
  empty,
  children,
}: {
  title: string;
  hint: string;
  count: number;
  tone: "danger" | "accent" | "warn" | "ok";
  empty: string;
  children: ReactNode;
}) {
  return (
    <section className={`kanban-col tone-${tone}`}>
      <header className="kanban-head">
        <h3>{title}</h3>
        <span className="badge role">{count}</span>
      </header>
      <p className="muted kanban-hint">{hint}</p>
      <div className="kanban-cards">
        {children}
        {count === 0 && <p className="kanban-empty">{empty}</p>}
      </div>
    </section>
  );
}

function Card({ children }: { children: ReactNode }) {
  return <div className="kanban-card">{children}</div>;
}

export default function MaintenancePage() {
  const [board, setBoard] = useState<MaintenanceBoard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const roles = currentRoles();
  const canDecide = roles.some((r) => ["fleet_admin", "fleet_manager"].includes(r));
  const canWork = roles.some((r) => ["fleet_admin", "fleet_manager", "technician"].includes(r));

  async function load() {
    setError(null);
    try {
      setBoard(await api.get<MaintenanceBoard>("/v1/maintenance/status?limit=200"));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function act(id: string, path: string, done: string) {
    setBusy(id);
    setError(null);
    setMessage(null);
    try {
      await api.post(path);
      setMessage(done);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(null);
    }
  }

  const b = board;

  return (
    <div>
      <PageHeader
        icon={<WrenchIcon />}
        title="Maintenance"
        subtitle="Where every service job stands, from proposal to serviced."
      />

      {b && (
        <StatGrid>
          <StatCard label="Awaiting approval" value={b.pending.length} icon={<ClockIcon width={15} height={15} />} tone="danger" />
          <StatCard label="Scheduled" value={b.scheduled.length} icon={<WrenchIcon width={15} height={15} />} tone="accent" />
          <StatCard label="In service now" value={b.in_service.length} icon={<TruckIcon width={15} height={15} />} tone="warn" />
          <StatCard
            label="Serviced this week"
            value={b.recent.filter((r) => r.status === "completed").length}
            icon={<TruckIcon width={15} height={15} />}
            tone="ok"
          />
        </StatGrid>
      )}

      {error && <p className="problem-banner">{error}</p>}
      {message && <p className="info-banner">{message}</p>}

      <div className="kanban">
        <Column
          title="Awaiting approval"
          hint="Proposed by the copilot. Approving books the nearest free depot."
          count={b?.pending.length ?? 0}
          tone="danger"
          empty="Nothing waiting."
        >
          {b?.pending.map((p) => (
            <Card key={p.work_order_id}>
              <Link to={`/vehicles/${p.vehicle_id}`} className="kanban-vin">
                {p.vin}
              </Link>
              <span>
                {p.failure_type ?? "—"} · risk {risk(p.risk_score)}
              </span>
              <span className="muted">
                {p.proposed_by} · {fmt(p.created_at)}
              </span>
              {canDecide && (
                <div className="kanban-actions">
                  <button
                    disabled={busy === p.work_order_id}
                    onClick={() =>
                      act(p.work_order_id, `/v1/work-orders/${p.work_order_id}/approve`, `${p.vin} approved and booked into a depot.`)
                    }
                  >
                    Approve
                  </button>
                  <button
                    className="secondary"
                    disabled={busy === p.work_order_id}
                    onClick={() => act(p.work_order_id, `/v1/work-orders/${p.work_order_id}/reject`, `${p.vin} proposal rejected.`)}
                  >
                    Reject
                  </button>
                </div>
              )}
            </Card>
          ))}
        </Column>

        <Column
          title="Scheduled"
          hint="Booked into a depot, not yet started."
          count={b?.scheduled.length ?? 0}
          tone="accent"
          empty="Book a vehicle from At-Risk Fleet."
        >
          {b?.scheduled.map((i) => (
            <Card key={i.booking_id}>
              <Link to={`/vehicles/${i.vehicle_id}`} className="kanban-vin">
                {i.vin}
              </Link>
              <span>
                {i.failure_type ?? "—"} · risk {risk(i.risk_score)}
              </span>
              <span className="muted">
                {i.depot_city} · bay held until {fmt(i.booked_until)}
              </span>
              {canWork && (
                <div className="kanban-actions">
                  <button
                    disabled={busy === i.work_order_id}
                    onClick={() => act(i.work_order_id, `/v1/maintenance/${i.work_order_id}/start`, `${i.vin} is now in service.`)}
                  >
                    Start service
                  </button>
                </div>
              )}
            </Card>
          ))}
        </Column>

        <Column
          title="In service"
          hint="At the depot being worked on now."
          count={b?.in_service.length ?? 0}
          tone="warn"
          empty="No vehicle in service."
        >
          {b?.in_service.map((i) => (
            <Card key={i.booking_id}>
              <Link to={`/vehicles/${i.vehicle_id}`} className="kanban-vin">
                {i.vin}
              </Link>
              <span>{i.failure_type ?? "—"}</span>
              <span className="muted">
                {i.depot_city} · started {fmt(i.started_at)}
              </span>
              {canWork && (
                <div className="kanban-actions">
                  <button
                    className="secondary"
                    disabled={busy === i.work_order_id}
                    onClick={() =>
                      act(i.work_order_id, `/v1/maintenance/${i.work_order_id}/complete`, `${i.vin} marked serviced. The depot bay is free again.`)
                    }
                  >
                    Mark serviced
                  </button>
                </div>
              )}
            </Card>
          ))}
        </Column>

        <Column title="Closed (7 days)" hint="Serviced or rejected." count={b?.recent.length ?? 0} tone="ok" empty="Nothing closed yet.">
          {b?.recent.map((r) => (
            <Card key={r.work_order_id}>
              <Link to={`/vehicles/${r.vehicle_id}`} className="kanban-vin">
                {r.vin}
              </Link>
              <span>
                <span className={`badge ${r.status === "completed" ? "sev-low" : "sev-medium"}`}>
                  {r.status === "completed" ? "Serviced" : "Rejected"}
                </span>{" "}
                {r.failure_type ?? "—"}
              </span>
              <span className="muted">
                {r.depot_city ?? "—"} · {fmt(r.closed_at)}
              </span>
            </Card>
          ))}
        </Column>
      </div>
      {loading && !b && <p className="muted">Loading…</p>}
    </div>
  );
}
