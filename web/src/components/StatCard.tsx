import type { ReactNode } from "react";

interface StatCardProps {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon: ReactNode;
  tone?: "accent" | "danger" | "warn" | "ok";
}

export function StatCard({ label, value, sub, icon, tone = "accent" }: StatCardProps) {
  return (
    <div className="stat-card">
      <div className="stat-top">
        <span className="stat-label">{label}</span>
        <span className={`stat-icon tone-${tone}`}>{icon}</span>
      </div>
      <span className="stat-value">{value}</span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  );
}

export function StatGrid({ children }: { children: ReactNode }) {
  return <div className="stat-grid">{children}</div>;
}
