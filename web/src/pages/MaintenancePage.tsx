import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { currentRoles } from "../lib/keycloak";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import SkeletonRows from "../components/SkeletonRows";
import { StatCard, StatGrid } from "../components/StatCard";
import { ClockIcon, TruckIcon, WrenchIcon } from "../components/icons";
import type { MaintenanceBoard } from "../types";

function fmt(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—";
}

function risk(score: number | null): string {
  return score !== null ? `${(score * 100).toFixed(1)}%` : "—";
}

function Section({
  title,
  hint,
  count,
  children,
}: {
  title: string;
  hint: string;
  count: number;
  children: ReactNode;
}) {
  return (
    <section>
      <h3 className="section-title">
        {title} <span className="badge role">{count}</span>
      </h3>
      <p className="muted">{hint}</p>
      {children}
    </section>
  );
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
  const skeleton = (cols: number) => loading && !b && <SkeletonRows columns={cols} />;

  return (
    <div>
      <PageHeader
        icon={<WrenchIcon />}
        title="Maintenance"
        subtitle="Where every service job stands: proposals waiting for a decision, vehicles booked, vehicles being serviced now, and what closed this week."
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

      <Section
        title="Awaiting approval"
        hint="Work orders proposed by the copilot. Approving one books the nearest depot with a free bay."
        count={b?.pending.length ?? 0}
      >
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>VIN</th>
                <th>Failure type</th>
                <th>Risk</th>
                <th>Proposed by</th>
                <th>Proposed</th>
                {canDecide && <th></th>}
              </tr>
            </thead>
            <tbody>
              {skeleton(canDecide ? 6 : 5)}
              {b?.pending.map((p) => (
                <tr key={p.work_order_id}>
                  <td>
                    <Link to={`/vehicles/${p.vehicle_id}`}>{p.vin}</Link>
                  </td>
                  <td>{p.failure_type ?? "—"}</td>
                  <td>{risk(p.risk_score)}</td>
                  <td>{p.proposed_by}</td>
                  <td>{fmt(p.created_at)}</td>
                  {canDecide && (
                    <td>
                      <button
                        disabled={busy === p.work_order_id}
                        onClick={() =>
                          act(p.work_order_id, `/v1/work-orders/${p.work_order_id}/approve`, `${p.vin} approved and booked into a depot.`)
                        }
                      >
                        Approve
                      </button>{" "}
                      <button
                        className="secondary"
                        disabled={busy === p.work_order_id}
                        onClick={() => act(p.work_order_id, `/v1/work-orders/${p.work_order_id}/reject`, `${p.vin} proposal rejected.`)}
                      >
                        Reject
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {b && b.pending.length === 0 && (
            <EmptyState icon={<ClockIcon width={32} height={32} />} title="Nothing waiting" detail="Copilot proposals will appear here for a decision." />
          )}
        </div>
      </Section>

      <Section title="Scheduled" hint="Booked into a depot, not yet started." count={b?.scheduled.length ?? 0}>
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
                {canWork && <th></th>}
              </tr>
            </thead>
            <tbody>
              {skeleton(canWork ? 7 : 6)}
              {b?.scheduled.map((i) => (
                <tr key={i.booking_id}>
                  <td>
                    <Link to={`/vehicles/${i.vehicle_id}`}>{i.vin}</Link>
                  </td>
                  <td>{i.failure_type ?? "—"}</td>
                  <td>{risk(i.risk_score)}</td>
                  <td>{i.depot_city}</td>
                  <td>{fmt(i.booked_from)}</td>
                  <td>{fmt(i.booked_until)}</td>
                  {canWork && (
                    <td>
                      <button
                        disabled={busy === i.work_order_id}
                        onClick={() => act(i.work_order_id, `/v1/maintenance/${i.work_order_id}/start`, `${i.vin} is now in service.`)}
                      >
                        Start service
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {b && b.scheduled.length === 0 && (
            <EmptyState
              icon={<WrenchIcon width={32} height={32} />}
              title="Nothing scheduled"
              detail="Book a vehicle from the At-Risk Fleet tab and it will appear here."
            />
          )}
        </div>
      </Section>

      <Section title="In service" hint="At the depot being worked on right now." count={b?.in_service.length ?? 0}>
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>VIN</th>
                <th>Failure type</th>
                <th>Depot</th>
                <th>Started</th>
                {canWork && <th></th>}
              </tr>
            </thead>
            <tbody>
              {skeleton(canWork ? 5 : 4)}
              {b?.in_service.map((i) => (
                <tr key={i.booking_id}>
                  <td>
                    <Link to={`/vehicles/${i.vehicle_id}`}>{i.vin}</Link>
                  </td>
                  <td>{i.failure_type ?? "—"}</td>
                  <td>{i.depot_city}</td>
                  <td>{fmt(i.started_at)}</td>
                  {canWork && (
                    <td>
                      <button
                        className="secondary"
                        disabled={busy === i.work_order_id}
                        onClick={() =>
                          act(i.work_order_id, `/v1/maintenance/${i.work_order_id}/complete`, `${i.vin} marked serviced. The depot bay is free again.`)
                        }
                      >
                        Mark serviced
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {b && b.in_service.length === 0 && (
            <EmptyState icon={<TruckIcon width={32} height={32} />} title="No vehicle in service" detail="Start a scheduled job to see it here." />
          )}
        </div>
      </Section>

      <Section title="Closed in the last 7 days" hint="Serviced or rejected." count={b?.recent.length ?? 0}>
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>VIN</th>
                <th>Failure type</th>
                <th>Outcome</th>
                <th>Depot</th>
                <th>Closed</th>
              </tr>
            </thead>
            <tbody>
              {skeleton(5)}
              {b?.recent.map((r) => (
                <tr key={r.work_order_id}>
                  <td>
                    <Link to={`/vehicles/${r.vehicle_id}`}>{r.vin}</Link>
                  </td>
                  <td>{r.failure_type ?? "—"}</td>
                  <td>
                    <span className={`badge ${r.status === "completed" ? "sev-low" : "sev-medium"}`}>
                      {r.status === "completed" ? "Serviced" : "Rejected"}
                    </span>
                  </td>
                  <td>{r.depot_city ?? "—"}</td>
                  <td>{fmt(r.closed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {b && b.recent.length === 0 && (
            <EmptyState
              icon={<WrenchIcon width={32} height={32} />}
              title="Nothing closed yet"
              detail="Serviced and rejected jobs show up here for a week."
            />
          )}
        </div>
      </Section>
    </div>
  );
}
