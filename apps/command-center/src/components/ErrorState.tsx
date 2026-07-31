export function ErrorState({ title, error }: { title: string; error?: string }) {
  return (
    <div className="error-state" role="alert">
      <strong>{title}</strong>
      {error ? <div style={{ marginTop: 8 }}>{error}</div> : null}
    </div>
  );
}
