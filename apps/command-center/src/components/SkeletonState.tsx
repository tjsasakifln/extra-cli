export function SkeletonState({ lines = 4 }: { lines?: number }) {
  return (
    <div className="skeleton-state" role="status" aria-busy="true" aria-label="Carregando">
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="skeleton-line"
          style={{ width: `${Math.max(40, 90 - i * 8)}%` }}
          aria-hidden="true"
        />
      ))}
    </div>
  );
}
