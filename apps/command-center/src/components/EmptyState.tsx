export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="empty-state" role="status">
      <strong>{title}</strong>
      {children ? <div style={{ marginTop: 8 }}>{children}</div> : null}
    </div>
  );
}
