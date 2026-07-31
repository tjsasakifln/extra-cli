import { useEffect, useState } from "react";
import { client } from "../api/client";
import { ConfirmationDialog } from "./ConfirmationDialog";

const FALLBACK_PHRASE =
  "Confirmo que revisei os dados e autorizo apenas a inclusão deste item na fila manual.";

export function DecisionPanel({
  itemId,
  title,
  evidence,
  limitations,
  risks,
  onDecided,
}: {
  itemId: string;
  title: string;
  evidence: string;
  limitations: string;
  risks: string;
  onDecided?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [phrase, setPhrase] = useState(FALLBACK_PHRASE);

  useEffect(() => {
    let cancelled = false;
    void client
      .reviewConfirmation(itemId)
      .then((res) => {
        if (!cancelled && res.confirmation_phrase) {
          setPhrase(String(res.confirmation_phrase));
        }
      })
      .catch(() => {
        /* keep fallback — server still enforces on submit */
      });
    return () => {
      cancelled = true;
    };
  }, [itemId]);

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
      // Never send sensitive/confirmation_phrase — backend owns them.
      const res = await client.saveDecision({
        item_id: itemId,
        decision: d,
        confirmation,
        rationale: title,
        payload: {
          evidence,
          limitations,
          risks,
        },
      });
      if (res.blocked) {
        setResult(String(res.message));
      } else {
        const label =
          d === "ACCEPT" ? "Aceito" : d === "REJECT" ? "Recusado" : "Adiado";
        setResult(`Decisão registrada: ${label}.`);
        onDecided?.();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setOpen(false);
    }
  };

  return (
    <div className="panel" style={{ boxShadow: "none", marginTop: 12 }}>
      <h3>Sua decisão</h3>
      <div className="stack" style={{ marginBottom: 12 }}>
        <div>
          <div className="muted" style={{ fontWeight: 600, fontSize: "0.82rem" }}>
            O que está em jogo
          </div>
          <p style={{ margin: "4px 0 0" }}>{title}</p>
        </div>
        <div>
          <div className="muted" style={{ fontWeight: 600, fontSize: "0.82rem" }}>
            Evidências (o que o sistema viu)
          </div>
          <p style={{ margin: "4px 0 0", whiteSpace: "pre-wrap" }}>{evidence}</p>
        </div>
        <div>
          <div className="muted" style={{ fontWeight: 600, fontSize: "0.82rem" }}>
            Limitações
          </div>
          <p style={{ margin: "4px 0 0", whiteSpace: "pre-wrap" }}>{limitations}</p>
        </div>
        <div>
          <div className="muted" style={{ fontWeight: 600, fontSize: "0.82rem" }}>
            Riscos se aceitar sem cuidado
          </div>
          <p style={{ margin: "4px 0 0", whiteSpace: "pre-wrap" }}>{risks}</p>
        </div>
      </div>
      <p className="muted" style={{ fontSize: "0.88rem" }}>
        O sistema <strong>nunca</strong> decide sozinho e <strong>não envia</strong> e-mail ou mensagem. Aceitar
        só registra a sua intenção localmente.
      </p>
      <div className="row">
        <button type="button" className="btn" onClick={() => request("REJECT")}>
          Recusar
        </button>
        <button type="button" className="btn" onClick={() => request("DEFER")}>
          Decidir depois
        </button>
        <button type="button" className="btn" onClick={() => request("ACCEPT")}>
          Aceitar com confirmação
        </button>
      </div>
      {result ? <p role="status">{result}</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      <ConfirmationDialog
        open={open}
        title="Confirmar aceite"
        description="Leia as limitações e riscos. Para aceitar, digite a frase abaixo exatamente como aparece."
        phrase={phrase}
        confirmLabel="Registrar aceite"
        dangerous
        onCancel={() => setOpen(false)}
        onConfirm={(typed) => void submit("ACCEPT", typed)}
      />
    </div>
  );
}
