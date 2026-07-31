import {
  attentionFromState,
  attentionLabel,
  attentionTokenClass,
  normalizeAttentionKind,
  type AttentionKind,
} from "../lib/status";

export function StatusBadge({
  state,
  attention,
  label,
  showTechnicalCode = false,
}: {
  state?: string | null;
  attention?: AttentionKind | string | null;
  label?: string;
  /** When true, append technical state code (prefer expandable detail elsewhere). */
  showTechnicalCode?: boolean;
}) {
  const kind: AttentionKind = attention
    ? normalizeAttentionKind(String(attention))
    : attentionFromState(state);
  const text = label || attentionLabel(kind);
  const cls = attentionTokenClass(kind);

  return (
    <span className={`status-badge ${cls}`} title={state ? `${text} (${state})` : text}>
      <span className="sr-only">Status: </span>
      <span className="status-badge__label">{text}</span>
      {showTechnicalCode && state ? (
        <span className="status-badge__code mono" aria-hidden="true">
          · {state}
        </span>
      ) : null}
    </span>
  );
}
