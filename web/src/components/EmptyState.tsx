import type { ReactNode } from "react";

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  detail?: string;
}

export default function EmptyState({ icon, title, detail }: EmptyStateProps) {
  return (
    <div className="empty-state">
      {icon}
      <span className="empty-title">{title}</span>
      {detail && <span className="empty-detail">{detail}</span>}
    </div>
  );
}
