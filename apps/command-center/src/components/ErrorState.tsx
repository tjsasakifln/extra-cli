export function ErrorState({
  title,
  error,
  onRetry,
}: {
  title: string;
  error?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="error-state panel" role="alert">
      <strong>{title}</strong>
      {error ? <div style={{ marginTop: 8 }} className="muted">{error}</div> : null}
      {onRetry ? (
        <div style={{ marginTop: 12 }}>
          <button type="button" className="btn btn-primary" onClick={onRetry}>
            Tentar novamente
          </button>
        </div>
      ) : null}
    </div>
  );
}
