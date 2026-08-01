import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { SkeletonState } from "../components/SkeletonState";

export function ComparePage() {
  const [params] = useSearchParams();
  const workflow = params.get("workflow") || "workflow.extra.opportunities";
  const currentParam = params.get("current") || "";

  const runsQ = useQuery({
    queryKey: ["runs-by-wf", workflow],
    queryFn: () => client.recentByWorkflow(workflow),
  });

  const current = currentParam || (runsQ.data?.runs?.[0]?.manifest_path as string | undefined) || "";
  const previous = (runsQ.data?.runs?.[1]?.manifest_path as string | undefined) || undefined;

  const compareQ = useQuery({
    queryKey: ["compare", current, previous, workflow],
    queryFn: () => client.compareRuns(current, previous, workflow),
    enabled: Boolean(current),
  });

  const diff = compareQ.data?.diff as Record<string, unknown> | undefined;
  const rows = (diff?.rows || null) as Record<string, unknown> | null;
  const counts = (rows?.counts || {}) as Record<string, number>;

  const summary = useMemo(() => {
    if (compareQ.data?.has_previous === false) return String(compareQ.data?.message || "");
    return String((diff?.summary as string) || "");
  }, [compareQ.data, diff]);

  return (
    <div>
      <header className="page-header">
        <h1>O que mudou desde o último ciclo</h1>
        <p>
          Comparação determinística entre duas execuções do mesmo fluxo: itens novos, removidos, alterados,
          scores e artefatos. Sem interpretações de “propensão”.
        </p>
      </header>

      <section className="panel">
        <h2>Fluxo</h2>
        <p className="mono">{workflow}</p>
        {runsQ.isLoading ? <SkeletonState /> : null}
        {(runsQ.data?.runs || []).length === 0 ? (
          <EmptyState title="Ainda não há execuções deste fluxo">
            <Link to={`/work/start/${encodeURIComponent(workflow)}`}>Executar agora</Link>
          </EmptyState>
        ) : (
          <ul>
            {(runsQ.data?.runs || []).slice(0, 5).map((r) => (
              <li key={String(r.job_id)}>
                <Link to={`/jobs/${String(r.job_id)}`}>{String(r.action || r.job_id)}</Link>
                <span className="muted"> · {String(r.finished_at || r.status)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {!current ? (
        <EmptyState title="Selecione ou execute um fluxo para comparar" />
      ) : compareQ.isLoading ? (
        <SkeletonState lines={6} />
      ) : compareQ.isError ? (
        <ErrorState title="Falha ao comparar" error={(compareQ.error as Error).message} />
      ) : (
        <section className="panel" style={{ marginTop: 16 }} aria-labelledby="diff-title">
          <h2 id="diff-title">Diferenças</h2>
          <p>{summary}</p>
          {compareQ.data?.has_previous ? (
            <div className="summary-grid">
              <div className="summary-chip">
                <span className="muted">Novos</span>
                <strong>{counts.added ?? 0}</strong>
              </div>
              <div className="summary-chip">
                <span className="muted">Removidos</span>
                <strong>{counts.removed ?? 0}</strong>
              </div>
              <div className="summary-chip">
                <span className="muted">Alterados</span>
                <strong>{counts.changed ?? 0}</strong>
              </div>
              <div className="summary-chip">
                <span className="muted">Run atual</span>
                <strong className="mono" style={{ fontSize: "0.75rem" }}>
                  {String((diff?.current_run_id as string) || "").slice(0, 8)}
                </strong>
              </div>
            </div>
          ) : null}
          {rows && Array.isArray(rows.added) && (rows.added as unknown[]).length > 0 ? (
            <div style={{ marginTop: 12 }}>
              <h3>Itens novos</h3>
              <ul>
                {(rows.added as Array<Record<string, unknown>>).slice(0, 20).map((r, i) => (
                  <li key={i}>{String(r.orgao || r.razao_social || r.id || r.nome || JSON.stringify(r).slice(0, 80))}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {rows && Array.isArray(rows.removed) && (rows.removed as unknown[]).length > 0 ? (
            <div style={{ marginTop: 12 }}>
              <h3>Itens removidos</h3>
              <ul>
                {(rows.removed as Array<Record<string, unknown>>).slice(0, 20).map((r, i) => (
                  <li key={i}>{String(r.orgao || r.razao_social || r.id || r.nome || JSON.stringify(r).slice(0, 80))}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {Array.isArray(diff?.artifacts && (diff.artifacts as { changed?: unknown[] }).changed) ? null : null}
          <details className="tech-details" style={{ marginTop: 12 }}>
            <summary>JSON técnico da comparação</summary>
            <pre className="log-stream">{JSON.stringify(compareQ.data, null, 2)}</pre>
          </details>
        </section>
      )}
    </div>
  );
}
