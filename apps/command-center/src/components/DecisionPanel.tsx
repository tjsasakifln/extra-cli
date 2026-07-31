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
  question,
  artifactHashes,
  onDecided,
}: {
  itemId: string;
  title: string;
  evidence: string;
  limitations: string;
  risks: string;
  question?: string;
  artifactHashes?: Record<string, string>;
  onDecided?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [phrase, setPhrase] = useState(FALLBACK_PHRASE);
  const [rationale, setRationale] = useState("");
  const [returnBy, setReturnBy] = useState("");
  const [pendingDecision, setPendingDecision] = useState<"ACCEPT" | "REJECT" | "DEFER" | null>(null);

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
    setError(null);
    if (d === "REJECT" || d === "DEFER") {
      if (rationale.trim().length < 8) {
        setError("Informe uma justificativa real (mínimo 8 caracteres). O título sozinho não basta.");
        return;
      }
      if (rationale.trim() === title.trim()) {
        setError("A justificativa não pode ser apenas o título do item.");
        return;
      }
    }
    if (d === "DEFER" && !returnBy.trim()) {
      setError("Ao adiar, informe data ou condição de retorno.");
      return;
    }
    if (d === "ACCEPT") {
      setPendingDecision("ACCEPT");
      setOpen(true);
      return;
    }
    void submit(d, "");
  };

  const submit = async (d: "ACCEPT" | "REJECT" | "DEFER", confirmation: string) => {
    setError(null);
    try {
      const hashes = artifactHashes || {};
      const res = await client.saveDecision({
        item_id: itemId,
        decision: d,
        confirmation,
        rationale: rationale.trim() || (d === "ACCEPT" ? `Aceite consciente: ${title}` : rationale),
        return_by: d === "DEFER" ? returnBy.trim() : undefined,
        artifact_hashes: hashes,
        payload: {
          evidence,
          limitations,
          risks,
          question,
          artifact_hashes: hashes,
          return_by: d === "DEFER" ? returnBy.trim() : undefined,
          no_auto_outreach: true,
        },
      });
      if (res.blocked) {
        setResult(String(res.message));
      } else {
        const label = d === "ACCEPT" ? "Aceito" : d === "REJECT" ? "Recusado" : "Adiado";
        setResult(`Decisão registrada: ${label}.`);
        onDecided?.();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setOpen(false);
      setPendingDecision(null);
    }
  };

  return (
    <div className="panel" style={{ boxShadow: "none", marginTop: 12 }}>
      <h3>Sua decisão</h3>
      <div className="stack" style={{ marginBottom: 12 }}>
        {question ? (
          <div>
            <div className="muted" style={{ fontWeight: 600, fontSize: "0.82rem" }}>
              Pergunta decisória
            </div>
            <p style={{ margin: "4px 0 0" }}>{question}</p>
          </div>
        ) : null}
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
        {artifactHashes && Object.keys(artifactHashes).length > 0 ? (
          <div>
            <div className="muted" style={{ fontWeight: 600, fontSize: "0.82rem" }}>
              Versão / hashes vinculados
            </div>
            <pre className="mono" style={{ fontSize: "0.75rem", whiteSpace: "pre-wrap" }}>
              {JSON.stringify(artifactHashes, null, 2)}
            </pre>
          </div>
        ) : null}
        <label className="field">
          <span>Justificativa (obrigatória em recusar/adiar)</span>
          <textarea
            rows={3}
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            placeholder="Descreva o motivo real da decisão"
          />
        </label>
        <label className="field">
          <span>Data ou condição de retorno (se adiar)</span>
          <input
            type="text"
            value={returnBy}
            onChange={(e) => setReturnBy(e.target.value)}
            placeholder="ex.: 2026-08-15 ou após nova coleta PNCP"
          />
        </label>
      </div>
      <p className="muted" style={{ fontSize: "0.88rem" }}>
        O sistema <strong>nunca</strong> decide sozinho e <strong>não envia</strong> e-mail ou mensagem. Aceitar
        só registra a sua intenção localmente, vinculada à versão exata das evidências.
      </p>
      {error ? <p className="error-text">{error}</p> : null}
      {result ? <p role="status">{result}</p> : null}
      <div className="row">
        <button type="button" className="btn" onClick={() => request("REJECT")}>
          Recusar
        </button>
        <button type="button" className="btn" onClick={() => request("DEFER")}>
          Adiar
        </button>
        <button type="button" className="btn btn-primary" onClick={() => request("ACCEPT")}>
          Aceitar
        </button>
      </div>
      <ConfirmationDialog
        open={open}
        title="Confirmar aceite"
        description="O aceite será vinculado aos hashes das evidências apresentadas. Alterações posteriores invalidam esta decisão."
        phrase={phrase}
        onCancel={() => {
          setOpen(false);
          setPendingDecision(null);
        }}
        onConfirm={(typed) => void submit(pendingDecision || "ACCEPT", typed)}
      />
    </div>
  );
}
