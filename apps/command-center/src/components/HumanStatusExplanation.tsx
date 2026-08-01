import { translateStatus } from "../lib/status";

export function HumanStatusExplanation({
  code,
  message,
  nextAction,
}: {
  code?: string | null;
  message?: string | null;
  nextAction?: string | null;
}) {
  const human = translateStatus(code, message);
  return (
    <div className="stack" style={{ gap: 6 }}>
      {code ? (
        <div className="mono muted" style={{ fontSize: "0.8rem" }}>
          {code}
        </div>
      ) : null}
      <p style={{ margin: 0 }}>{human}</p>
      {nextAction ? (
        <p style={{ margin: 0 }} className="muted">
          <strong>Próxima ação:</strong> {nextAction}
        </p>
      ) : null}
    </div>
  );
}
