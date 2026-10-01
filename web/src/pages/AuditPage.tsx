import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import SkeletonRows from "../components/SkeletonRows";
import { ListIcon } from "../components/icons";
import type { AuditLogEntry } from "../types";

export default function AuditPage() {
  const [rows, setRows] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<AuditLogEntry[]>("/v1/audit?limit=100")
      .then(setRows)
      .catch((err) => setError(err instanceof ApiError ? err.detail : String(err)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <PageHeader
        icon={<ListIcon />}
        title="Audit Log"
        subtitle="A record of every action taken in the app. Visible to fleet admins and auditors."
      />
      {error && <p className="problem-banner">{error}</p>}
      <div className="table-card">
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Actor</th>
              <th>Action</th>
              <th>Resource</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {loading && rows.length === 0 && <SkeletonRows columns={5} />}
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{new Date(r.created_at).toLocaleString()}</td>
                <td>{r.actor}</td>
                <td>{r.action}</td>
                <td className="mono">{r.resource}</td>
                <td style={{ fontSize: 12 }} className="mono muted">
                  {JSON.stringify(r.details)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && rows.length === 0 && !error && (
          <EmptyState icon={<ListIcon width={32} height={32} />} title="No audit entries yet" />
        )}
      </div>
    </div>
  );
}
