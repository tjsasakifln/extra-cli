import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { ConfirmationDialog } from "../components/ConfirmationDialog";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { SkeletonState } from "../components/SkeletonState";
// useQuery already imported above

type WfParam = {
  name: string;
  label: string;
  type: string;
  required?: boolean;
  default?: unknown;
  choices?: string[];
  description?: string;
  advanced?: boolean;
};

type Workflow = {
  id: string;
  title: string;
  subtitle: string;
  client_label: string;
  outcome: string;
  description: string;
  steps: string[];
  expected_deliverables: string[];
  params: WfParam[];
  limitations: string[];
  preflight?: Record<string, unknown>;
};

export function WorkStartPage() {
  const { workflowId } = useParams();
  const navigate = useNavigate();
  const listQ = useQuery({ queryKey: ["workflows"], queryFn: client.workflows });
  const detailQ = useQuery({
    queryKey: ["workflow", workflowId],
    queryFn: () => client.workflow(String(workflowId)),
    enabled: Boolean(workflowId),
  });

  if (!workflowId) {
    return <WorkCatalog workflows={(listQ.data?.workflows || []) as Workflow[]} loading={listQ.isLoading} error={listQ.error as Error | null} />;
  }

  if (detailQ.isLoading) return <SkeletonState lines={10} />;
  if (detailQ.isError) return <ErrorState title="Fluxo indisponível" error={(detailQ.error as Error).message} />;
  const wf = detailQ.data as Workflow;
  return <WorkPreflight workflow={wf} onStarted={(jobId) => navigate(`/jobs/${jobId}`)} />;
}

function WorkCatalog({
  workflows,
  loading,
  error,
}: {
  workflows: Workflow[];
  loading: boolean;
  error: Error | null;
}) {
  return (
    <div>
      <header className="page-header">
        <h1>Iniciar trabalho</h1>
        <p>
          Escolha o resultado de negócio que você precisa. O sistema monta o caminho, gera entregáveis
          profissionais e abre a revisão — sem terminal e sem digitar pastas.
        </p>
      </header>
      {loading ? <SkeletonState /> : null}
      {error ? <ErrorState title="Não foi possível listar fluxos" error={error.message} /> : null}
      {!loading && workflows.length === 0 ? (
        <EmptyState title="Nenhum fluxo cadastrado" />
      ) : (
        <div className="grid-actions">
          {workflows
            .filter((w) => w.id !== "workflow.review.pending")
            .map((w) => (
              <Link key={w.id} className="action-card" to={`/work/start/${encodeURIComponent(w.id)}`}>
                <strong>{w.title}</strong>
                <span className="muted">{w.subtitle}</span>
                <span className="muted" style={{ fontSize: "0.85rem" }}>
                  {w.client_label} · {w.outcome}
                </span>
                <span className="btn" style={{ alignSelf: "flex-start", pointerEvents: "none" }}>
                  Configurar e executar
                </span>
              </Link>
            ))}
        </div>
      )}
      <p style={{ marginTop: 20 }}>
        <Link to="/actions">Área avançada (capabilities técnicas)</Link>
      </p>
    </div>
  );
}

function WorkPreflight({ workflow, onStarted }: { workflow: Workflow; onStarted: (jobId: string) => void }) {
  const defaults = useMemo(() => {
    const d: Record<string, unknown> = {};
    for (const p of workflow.params || []) {
      if (p.default !== undefined && p.default !== null) d[p.name] = p.default;
    }
    return d;
  }, [workflow.params]);
  const [params, setParams] = useState<Record<string, unknown>>(defaults);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const capQ = useQuery({
    queryKey: ["capability", workflow.id],
    queryFn: () => client.capability(workflow.id),
  });
  const phrase =
    (capQ.data?.confirmation_phrase as string | undefined) ||
    "Confirmo a geração local de entregáveis (sem envio automático de mensagens).";

  const basicParams = (workflow.params || []).filter((p) => !p.advanced);
  const advancedParams = (workflow.params || []).filter((p) => p.advanced);

  const run = async (confirmation: string) => {
    setBusy(true);
    setError(null);
    try {
      // Only send declared params (server rejects unknown keys)
      const allowed = new Set((workflow.params || []).map((p) => p.name));
      // Prefer capability param list when loaded (authoritative allowlist)
      const capParams = capQ.data?.params?.map((p) => p.name) || [];
      const allow = capParams.length ? new Set(capParams) : allowed;
      const payload: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(params)) {
        if (!allow.has(k)) continue;
        if (v === undefined || v === null || v === "") continue;
        payload[k] = v;
      }
      for (const p of workflow.params || []) {
        if (!allow.has(p.name)) continue;
        if (p.type === "bool" && payload[p.name] !== undefined) {
          payload[p.name] = Boolean(payload[p.name]);
        }
        if (p.type === "int" && payload[p.name] !== undefined && payload[p.name] !== "") {
          payload[p.name] = Number(payload[p.name]);
        }
      }
      // ensure bool defaults that are true are sent (unchecked would omit)
      for (const p of workflow.params || []) {
        if (p.type === "bool" && allow.has(p.name) && payload[p.name] === undefined && p.default === true) {
          payload[p.name] = true;
        }
      }
      const res = await client.startJob(workflow.id, payload, confirmation);
      const jobId = res.job?.job_id;
      if (!jobId) throw new Error("Job não retornou identificador");
      onStarted(jobId);
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
        <p className="muted" style={{ marginBottom: 4 }}>
          <Link to="/work/start">Iniciar trabalho</Link> / {workflow.client_label}
        </p>
        <h1>{workflow.title}</h1>
        <p>{workflow.description}</p>
      </header>

      <section className="panel" aria-labelledby="preflight-title">
        <h2 id="preflight-title">Antes de executar</h2>
        <div className="summary-grid">
          <div className="summary-chip">
            <span className="muted">Objetivo</span>
            <strong>{workflow.outcome}</strong>
          </div>
          <div className="summary-chip">
            <span className="muted">Cliente / frente</span>
            <strong>{workflow.client_label}</strong>
          </div>
          <div className="summary-chip">
            <span className="muted">Outreach automático</span>
            <strong>Não — nunca</strong>
          </div>
        </div>
        <h3>Etapas</h3>
        <ol>
          {workflow.steps.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ol>
        <h3>Entregáveis esperados</h3>
        <ul>
          {workflow.expected_deliverables.map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
        <h3>Limitações</h3>
        <ul>
          {(workflow.limitations || []).map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
        <p className="muted">
          Caminhos de saída são gerados automaticamente em pasta segura do Command Center. Você não precisa
          digitar diretórios.
        </p>
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Parâmetros</h2>
        <div className="stack">
          {basicParams.map((p) => (
            <ParamField key={p.name} param={p} value={params[p.name]} onChange={(v) => setParams((prev) => ({ ...prev, [p.name]: v }))} />
          ))}
        </div>
        {advancedParams.length > 0 ? (
          <div style={{ marginTop: 12 }}>
            <button type="button" className="btn" onClick={() => setShowAdvanced((v) => !v)}>
              {showAdvanced ? "Ocultar opções avançadas" : "Mostrar opções avançadas"}
            </button>
            {showAdvanced ? (
              <div className="stack" style={{ marginTop: 12 }}>
                {advancedParams.map((p) => (
                  <ParamField
                    key={p.name}
                    param={p}
                    value={params[p.name]}
                    onChange={(v) => setParams((prev) => ({ ...prev, [p.name]: v }))}
                  />
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      {error ? <ErrorState title="Não foi possível iniciar" error={error} /> : null}

      <div className="row" style={{ marginTop: 16, gap: 12 }}>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => setConfirmOpen(true)}>
          {busy ? "Iniciando…" : "Gerar entregáveis"}
        </button>
        <Link className="btn" to="/work/start">
          Voltar
        </Link>
      </div>

      <ConfirmationDialog
        open={confirmOpen}
        title="Confirmar geração local"
        phrase={phrase}
        description={`Será gerado o pacote de ${workflow.client_label} com PDF/XLSX quando aplicável. Nenhum e-mail ou WhatsApp será enviado.`}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={(typed) => void run(typed)}
      />
    </div>
  );
}

function ParamField({
  param,
  value,
  onChange,
}: {
  param: WfParam;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  if (param.type === "bool") {
    return (
      <label className="field">
        <span>{param.label}</span>
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
        />
        {param.description ? <span className="muted">{param.description}</span> : null}
      </label>
    );
  }
  if (param.type === "select" && param.choices?.length) {
    return (
      <label className="field">
        <span>{param.label}</span>
        <select value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>
          {param.choices.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        {param.description ? <span className="muted">{param.description}</span> : null}
      </label>
    );
  }
  return (
    <label className="field">
      <span>{param.label}</span>
      <input
        type={param.type === "int" ? "number" : "text"}
        value={value === undefined || value === null ? "" : String(value)}
        onChange={(e) =>
          onChange(param.type === "int" ? (e.target.value === "" ? null : Number(e.target.value)) : e.target.value)
        }
      />
      {param.description ? <span className="muted">{param.description}</span> : null}
    </label>
  );
}
