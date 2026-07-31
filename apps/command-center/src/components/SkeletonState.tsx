export function SkeletonState({ lines = 4 }: { lines?: number }) {
  return (
    <div className="skeleton-state" aria-busy="true" aria-label="Carregando">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton-line" style={{ width: `${90 - i * 8}%` }} />
      ))}
    </div>
  );
}
