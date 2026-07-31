export function CoverageBar({
  numerator,
  denominator,
  label,
}: {
  numerator: number;
  denominator: number;
  label: string;
}) {
  const pct = denominator > 0 ? Math.min(100, Math.round((numerator / denominator) * 1000) / 10) : 0;
  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span>{label}</span>
        <span className="mono muted">
          {numerator} de {denominator} ({pct}%)
        </span>
      </div>
      <div
        className="coverage-bar"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={denominator || 100}
        aria-valuenow={numerator}
        aria-valuetext={`${numerator} de ${denominator}`}
      >
        <span style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
