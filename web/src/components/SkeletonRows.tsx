// Shimmering placeholder rows instead of a blank table while the first page
// of data loads — AtRiskPage/AlertsPage/AuditPage all had a moment where the
// table just rendered with a header and nothing under it.
export default function SkeletonRows({ columns, rows = 5 }: { columns: number; rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <tr className="skeleton-row" key={r}>
          {Array.from({ length: columns }).map((__, c) => (
            <td key={c}>
              <div className="skeleton-bar" style={{ width: c === 0 ? "70%" : "50%" }} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
