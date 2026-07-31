import { useState } from "react";
import { client } from "../api/client";
import { ConfirmationDialog } from "./ConfirmationDialog";

const DEFAULT_PHRASE =
  "Confirmo que revisei os dados e autorizo apenas a inclusão deste item na fila manual.";

export function DecisionPanel({
  itemId,
  title,
  evidence,
  limitations,
  risks,
}: {
  itemId: string;
  title: string;
  evidence: string;
  limitations: string;
  risks: string;
}) {
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const request = (d: "ACCEPT" | "REJECT" | "DEFER") => {
    if (d === "ACCEPT") {
      setOpen(true);
    } else {
      void submit(d, "");
    }
  };

  const submit = async (d: "ACCEPT" | "REJECT" | "DEFER", confirmation: string) => {
    setError(null);
    try {
      const res = await client.saveDecision({
        item_id: itemId,
        decision: d,
        confirmation,
        rationale: title,
        payload: {
          sensitive: d === "ACCEPT",
          confirmation_phrase: DEFAULT_PHRASE,
          evidence,
          limitations,
          risks,
        },
      });
      if (res.blocked) {
        setResult(String(res.message));
      } else {
        setResult(`Decisão ${d} registrada (${res.decision_id}).`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setOpen(false);
    }
  };

  return (
    <div className="panel">
      <h3>Revisão humana</h3>
      <p>
        <strong>O que está sendo decidido:</strong> {title}
      </p>
      <p>
        <strong>Evidências:</strong> {evidence}
      </p>
      <p>
        <strong>Limitações:</strong> {limitations}
      </p>
      <p>
        <strong>Riscos:</strong> {risks}
      </p>
      <p className="muted">
        ACCEPT não é destacado como ação “segura”. Nenhuma decisão é tomada por você automaticamente.
      </p>
      <div className="row">
        <button type="button" className="btn" onClick={() => request("REJECT")}>
          REJECT
        </button>
        <button type="button" className="btn" onClick={() => request("DEFER")}>
          DEFER
        </button>
        <button type="button" className="btn" onClick={() => request("ACCEPT")}>
          ACCEPT
        </button>
      </div>
      {result ? <p role="status">{result}</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      <ConfirmationDialog
        open={open}
        title="Confirmar ACCEPT"
        description="Esta decisão pode afetar fila comercial ou classificação. Leia as limitações antes de confirmar."
        phrase={DEFAULT_PHRASE}
        confirmLabel="Registrar ACCEPT"
        dangerous
        onCancel={() => setOpen(false)}
        onConfirm={(typed) => void submit("ACCEPT", typed)}
      />
    </div>
  );
}
