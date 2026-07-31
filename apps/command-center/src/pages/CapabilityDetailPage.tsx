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
  if (q.isError || !q.data) {
    return <ErrorState title="Ação não encontrada" error={(q.error as Error)?.message} />;
  }

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
          <Link to="/actions">Todas as ações</Link> / {cap.name}
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
              label={available ? "Pronta para usar" : "Indisponível neste computador"}
            />
            <span className={`risk-chip ${cap.risk}`}>{riskLabel(cap.risk)}</span>
          </div>
          {!available ? (
            <p>
              {cap.unavailable_reason ||
                "Esta ação ainda não está disponível na instalação atual. As demais continuam funcionando."}
            </p>
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
                {cap.risk === "read"
                  ? "Somente consulta — não altera dados comerciais."
                  : "Pode gerar arquivos e listas neste computador. Não envia mensagem a clientes sozinha."}
              </p>
              <div className="row">
                <button
                  type="button"
                  className="btn btn-primary btn-lg"
                  disabled={busy}
                  onClick={() => {
                    if (cap.requires_confirmation) setConfirmOpen(true);
                    else void run();
                  }}
                >
                  {busy ? "Iniciando…" : "Executar agora"}
                </button>
              </div>
              {error ? <p role="alert">{error}</p> : null}
            </>
          )}
        </section>
        <section className="panel">
          <h2>O que esperar</h2>
          <ul>
            <li>Você acompanha o progresso na tela de atividade.</li>
            <li>Quando terminar, os resultados abrem em tabela ou arquivo para download.</li>
            <li>Se precisar de decisão humana, o item entra em <Link to="/review">Revisões</Link>.</li>
            {(cap.required_env || []).length > 0 ? (
              <li>Requer configuração: {(cap.required_env || []).map(friendlyEnv).join(", ")}</li>
            ) : (
              <li>Não exige credenciais extras além do ambiente local.</li>
            )}
          </ul>
          <details className="tech-details">
            <summary>Detalhes técnicos (opcional)</summary>
            <ul>
              <li>
                ID: <span className="mono">{cap.id}</span>
              </li>
              <li>Categoria: {cap.category}</li>
              <li>Confirmação: {cap.requires_confirmation ? "sim" : "não"}</li>
              <li>Pode cancelar: {cap.allow_cancel ? "sim" : "não"}</li>
              <li>Saídas: {(cap.output_roots || []).join(", ") || "—"}</li>
            </ul>
          </details>
        </section>
      </div>

      <ConfirmationDialog
        open={confirmOpen}
        title={`Confirmar: ${cap.name}`}
        description="Revise o efeito antes de executar. O painel não envia outreach e não decide por você."
        phrase={cap.confirmation_phrase || "CONFIRMO"}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={(typed) => void run(typed)}
      />
    </div>
  );
}

function riskLabel(risk: string): string {
  const map: Record<string, string> = {
    read: "Somente leitura",
    write_local: "Gera arquivos locais",
    human_decision: "Exige decisão humana",
    destructive: "Potencialmente destrutivo",
  };
  return map[risk] || risk;
}

function friendlyEnv(key: string): string {
  if (key.includes("DATALAKE") || key.includes("DATABASE")) return "banco de dados local";
  if (key.includes("OPENAI")) return "chave de IA";
  return key;
}
