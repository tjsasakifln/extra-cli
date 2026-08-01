import { useState } from "react";

export function ConfirmationDialog({
  open,
  title,
  description,
  phrase,
  confirmLabel = "Confirmar",
  onCancel,
  onConfirm,
  dangerous = false,
}: {
  open: boolean;
  title: string;
  description: string;
  phrase?: string | null;
  confirmLabel?: string;
  onCancel: () => void;
  onConfirm: (typed: string) => void;
  dangerous?: boolean;
}) {
  const [typed, setTyped] = useState("");
  if (!open) return null;
  const needsPhrase = Boolean(phrase);
  const canConfirm = !needsPhrase || typed.trim() === phrase;
  return (
    <div className="dialog-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="confirm-title">{title}</h2>
        <p>{description}</p>
        {phrase ? (
          <div className="field">
            <label htmlFor="confirm-phrase">Digite exatamente a frase de confirmação</label>
            <input
              id="confirm-phrase"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoFocus
              aria-describedby="confirm-phrase-hint"
            />
            <div id="confirm-phrase-hint" className="hint mono">
              {phrase}
            </div>
          </div>
        ) : null}
        <div className="row" style={{ justifyContent: "flex-end", marginTop: 16 }}>
          <button type="button" className="btn" onClick={onCancel}>
            Cancelar
          </button>
          <button
            type="button"
            className={dangerous ? "btn btn-danger" : "btn btn-primary"}
            disabled={!canConfirm}
            onClick={() => onConfirm(typed)}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
