import type { ReactNode } from "react";

interface PageHeaderProps {
  icon: ReactNode;
  title: string;
  subtitle?: ReactNode;
}

// Every page repeated the same `<h2>` + muted subtitle pattern by hand
// (AtRiskPage, AlertsPage, CopilotPage, ...) — one shared component so the
// icon treatment and spacing stay consistent instead of drifting per page.
export default function PageHeader({ icon, title, subtitle }: PageHeaderProps) {
  return (
    <div className="page-header">
      <div className="page-header-icon">{icon}</div>
      <div className="page-header-text">
        <h2>{title}</h2>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
    </div>
  );
}
