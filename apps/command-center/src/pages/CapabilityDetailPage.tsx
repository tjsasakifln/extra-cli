import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { ConfirmationDialog } from "../components/ConfirmationDialog";
import { ErrorState } from "../components/ErrorState";
import { ParameterForm } from "../components/ParameterForm";
import { SkeletonState } from "../components/SkeletonState";
import { StatusBadge } from "../components/StatusBadge";

export function CapabilityDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["capability", id], queryFn: () => client.capability(id), enabled: Boolean(id) });
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [advanced, setAdvanced] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (q.isLoading) return <SkeletonState />;
  if (q.isError || !q.data) return <ErrorState title="Capability não encontrada" error={(q.error as Error)?.message} />;

  const cap = q.data;
  const available = cap.availability === "available";

  const run = async (confirmation?: string) => {
    setBusy(true);
    setError(null);
    try {
      const params: Record<string, unknown> = {};
      for (const p of cap.params) {
        const v = values[p.name] ?? p.default;
        if (v !== undefined && v !== null && v !== "") params[p.name] = v;
      }
      const res = await client.startJob(cap.id, params, confirmation);
      navigate(`/jobs/${res.job.job_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      setConfirmOpen(false);
    }
  };

  return (
    <div>
      <header className="page-header">
        <p className="muted" style={{ marginBottom: 8 }}>
          <Link to="/capabilities">Capabilities</Link> / {cap.id}
        </p>
        <h1>{cap.name}</h1>
        <p>{cap.description}</p>
      </header>

      <div className="grid-2">
        <section className="panel">
          <div className="row" style={{ marginBottom: 12 }}>
            <StatusBadge
              state={available ? "SUCCEEDED" : "UNAVAILABLE"}
              attention={available ? "healthy" : "no_data"}
              label={available ? "Disponível" : "Ainda não disponível nesta versão"}
            />
            <span className="muted">{cap.risk}</span>
          </div>
          {!available ? (
            <p>{cap.unavailable_reason || "Capability ausente neste branch."}</p>
          ) : (
            <>
              <ParameterForm
                capability={cap}
                values={values}
                onChange={(name, value) => setValues((v) => ({ ...v, [name]: value }))}
                showAdvanced={advanced}
                onToggleAdvanced={() => setAdvanced((a) => !a)}
              />
              <p className="muted">
                Esta ação {cap.risk === "read" ? "é somente leitura." : "pode gerar artefatos locais."} Não envia
                mensagens nem altera sistemas externos por padrão.
              </p>
              <div className="row">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() => {
                    if (cap.requires_confirmation) setConfirmOpen(true);
                    else void run();
                  }}
                >
                  Executar
                </button>
              </div>
              {error ? <p role="alert">{error}</p> : null}
            </>
          )}
        </section>
        <section className="panel">
          <h2>Detalhes técnicos</h2>
          <ul>
            <li>
              ID: <span className="mono">{cap.id}</span>
            </li>
            <li>Categoria: {cap.category}</li>
            <li>Confirmação: {cap.requires_confirmation ? "sim" : "não"}</li>
            <li>Cancelável: {cap.allow_cancel ? "sim" : "não"}</li>
            <li>Env: {(cap.required_env || []).join(", ") || "—"}</li>
            <li>Outputs: {(cap.output_roots || []).join(", ") || "—"}</li>
          </ul>
        </section>
      </div>

      <ConfirmationDialog
        open={confirmOpen}
        title={`Confirmar: ${cap.name}`}
        description="Revise o efeito antes de executar. O Command Center não decide por você."
        phrase={cap.confirmation_phrase}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={(typed) => void run(typed)}
      />
    </div>
  );
}
