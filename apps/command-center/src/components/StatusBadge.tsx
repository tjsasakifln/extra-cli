import { attentionFromState, attentionLabel, type AttentionKind } from "../lib/status";

export function StatusBadge({
  state,
  attention,
  label,
}: {
  state?: string | null;
  attention?: AttentionKind | string | null;
  label?: string;
}) {
  const kind = (attention as AttentionKind) || attentionFromState(state);
  const text = label || attentionLabel(kind);
  return (
    <span className={`status-badge status-${kind}`} title={state || text}>
      <span className="sr-only">Status: </span>
      {text}
      {state ? <span className="mono" style={{ opacity: 0.75, fontWeight: 500 }}>
        · {state}
      </span> : null}
    </span>
  );
}
