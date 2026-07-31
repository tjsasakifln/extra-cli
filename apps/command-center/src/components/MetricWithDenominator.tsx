export function MetricWithDenominator({
  label,
  value,
  denominator,
  unitLabel,
  description,
}: {
  label: string;
  value: number | string;
  denominator?: number | string | null;
  unitLabel?: string;
  description?: string;
}) {
  return (
    <div className="metric" role="group" aria-label={label}>
      <div className="muted" style={{ fontSize: "0.82rem", fontWeight: 600 }}>
        {label}
      </div>
      <div className="value">
        {value}
        {denominator !== undefined && denominator !== null ? (
          <span className="denom"> de {denominator}</span>
        ) : null}
      </div>
      {unitLabel ? <div className="denom">{unitLabel}</div> : null}
      {description ? <div className="muted" style={{ fontSize: "0.8rem" }}>{description}</div> : null}
    </div>
  );
}
