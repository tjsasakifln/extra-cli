import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { MetricWithDenominator } from "../components/MetricWithDenominator";
import { SkeletonState } from "../components/SkeletonState";
import { StatusBadge } from "../components/StatusBadge";
import { formatWhen } from "../lib/format";
import { normalizeAttentionKind } from "../lib/status";

type AttentionItem = {
  kind: string;
  title: string;
  detail?: string;
  href: string;
  priority?: number;
  count?: number;
  next_action?: string;
};

export function HomePage() {
  const q = useQuery({
    queryKey: ["overview"],
    queryFn: ({ signal }) => client.overview(signal),
    refetchInterval: 10000,
  });

  if (q.isLoading) return <SkeletonState lines={8} />;
  if (q.isError) {
    return (
      <ErrorState
        title="Não foi possível carregar o painel"
        error={(q.error as Error).message}
        onRetry={() => void q.refetch()}
      />
    );
  }

  const data = q.data as {
    headline: string;
    attention: AttentionItem[];
    capabilities: { total: number; available: number; unavailable: number };
    jobs: { recent: Array<Record<string, unknown>>; counts: Record<string, number> };
    quick_actions: Array<{ id: string; label: string; href: string; blurb?: string }>;
    areas: Array<{ id: string; label: string; href: string; blurb?: string }>;
    health: { sha: string; env: Record<string, string>; profile: string };
    reviews_pending_count?: number;
    what_changed?: Array<{ workflow_id: string; label: string; href: string; finished_at?: string }>;
    deliverables_recent?: Array<{ path: string; action: string; href: string }>;
  };

  const attentionTop = (data.attention || []).slice(0, 5);
  const attentionRest = (data.attention || []).length - attentionTop.length;
  const reviewCount = data.reviews_pending_count ?? 0;

  return (
    <div>
      <header className="page-header">
        <h1>O que fazer agora?</h1>
        <p>
          Este é o seu centro de operação da consultoria: gerar listas, abrir resultados em tabela, revisar o
          que precisa de decisão humana e acompanhar o que está rodando — tudo com um clique, sem terminal.
        </p>
      </header>

      <section className="hero-panel" aria-labelledby="attention-title">
        <h2 id="attention-title" style={{ marginTop: 0 }}>
          {data.headline}
        </h2>
        {attentionTop.length === 0 ? (
          <EmptyState title="Nada urgente no momento">
            Use «Iniciar novo trabalho» abaixo para gerar uma lista ou abrir resultados recentes.
          </EmptyState>
        ) : (
          <div className="stack">
            {attentionTop.map((item, idx) => {
              const kind = normalizeAttentionKind(item.kind);
              const openLabel = item.count
                ? `Abrir fila com ${item.count} revisões`
                : `Abrir: ${item.title}`;
              return (
                <div className="attention-item" key={`${item.title}-${idx}`}>
                  <StatusBadge attention={kind} />
                  <div>
                    <strong>{item.title}</strong>
                    {item.detail ? <div className="muted">{item.detail}</div> : null}
                    {item.next_action ? (
                      <div className="muted">Próxima ação: {item.next_action}</div>
                    ) : null}
                  </div>
                  <Link className="btn btn-primary" to={item.href} aria-label={openLabel}>
                    {item.count ? `Ver ${item.count}` : "Abrir"}
                  </Link>
                </div>
              );
            })}
            {attentionRest > 0 ? (
              <p className="muted">
                +{attentionRest} itens. <Link to="/jobs">Ver lista completa de atividades</Link>
              </p>
            ) : null}
          </div>
        )}
      </section>

      <section style={{ marginTop: 20 }} aria-labelledby="start-work-home">
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
          <h2 id="start-work-home" style={{ margin: 0 }}>
            Iniciar novo trabalho
          </h2>
          <Link className="btn btn-primary" to="/work/start">
            Ver todos os fluxos
          </Link>
        </div>
        <div className="grid-actions">
          {data.quick_actions.map((a) => (
            <Link
              key={a.id}
              className="action-card"
              to={a.href}
              aria-label={`Iniciar fluxo ${a.label}`}
            >
              <strong>{a.label}</strong>
              <span className="muted">{a.blurb || "Abrir fluxo guiado"}</span>
            </Link>
          ))}
        </div>
      </section>

      <section style={{ marginTop: 20 }} className="panel" aria-labelledby="reviews-home">
        <h2 id="reviews-home" style={{ marginTop: 0 }}>
          Revisões pendentes
        </h2>
        <p>
          {reviewCount > 0 ? (
            <>
              <strong>{reviewCount}</strong> item(ns) aguardando sua decisão.{" "}
              <Link to="/review" aria-label={`Abrir fila com ${reviewCount} revisões`}>
                Abrir fila de revisão
              </Link>
            </>
          ) : (
            <>
              Nada pendente. <Link to="/review">Ver histórico de revisões</Link>
            </>
          )}
        </p>
      </section>

      <section style={{ marginTop: 20 }} className="panel" aria-labelledby="changed-home">
        <h2 id="changed-home" style={{ marginTop: 0 }}>
          Mudanças desde o último ciclo
        </h2>
        {(data.what_changed || []).length === 0 ? (
          <EmptyState title="Execute um fluxo guiado duas vezes para ver o que mudou">
            <Link to="/compare">Abrir comparação</Link>
          </EmptyState>
        ) : (
          <div className="stack">
            {(data.what_changed || []).map((w) => {
              const when = formatWhen(w.finished_at);
              return (
                <div className="row" key={w.workflow_id} style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                  <div>
                    <strong>{w.label}</strong>
                    <div className="muted" title={when.title}>
                      {when.text}
                    </div>
                  </div>
                  <Link
                    className="btn"
                    to={w.href || `/compare?workflow=${encodeURIComponent(w.workflow_id)}`}
                    aria-label={`Comparar execução de ${w.label}`}
                  >
                    Comparar
                  </Link>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section style={{ marginTop: 20 }} className="panel" aria-labelledby="deliverables-home">
        <h2 id="deliverables-home" style={{ marginTop: 0 }}>
          Entregáveis recentes
        </h2>
        {(data.deliverables_recent || []).length === 0 ? (
          <EmptyState title="Nenhum PDF/XLSX recente">
            <Link to="/work/start">Gerar entregáveis</Link>
          </EmptyState>
        ) : (
          <ul>
            {(data.deliverables_recent || []).slice(0, 6).map((d) => (
              <li key={d.path}>
                <Link to={d.href} aria-label={`Abrir entregável ${d.path.split(/[/\\]/).pop()}`}>
                  {d.path.split(/[/\\]/).pop()}
                </Link>
                <span className="muted"> · {d.action}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section style={{ marginTop: 20 }} className="panel">
        <h2 style={{ marginTop: 0 }}>Continuar de onde parei</h2>
        {(data.jobs.recent || []).length === 0 ? (
          <EmptyState title="Nenhuma atividade recente">
            Inicie um fluxo em «Iniciar novo trabalho».
          </EmptyState>
        ) : (
          <div className="stack">
            {(data.jobs.recent || []).slice(0, 3).map((j) => (
              <div
                className="row"
                key={String(j.job_id)}
                style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}
              >
                <div>
                  <strong>{String(j.action)}</strong>
                  <div className="muted">{String(j.human_message || j.status)}</div>
                </div>
                <Link
                  className="btn"
                  to={`/jobs/${String(j.job_id)}`}
                  aria-label={`Abrir job ${String(j.action)}`}
                >
                  Abrir
                </Link>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="grid-2" style={{ marginTop: 20 }}>
        <section className="panel">
          <h2>Áreas de trabalho</h2>
          <div className="stack">
            {data.areas.map((area) => (
              <Link
                key={area.id}
                to={area.href}
                className="row"
                style={{
                  textDecoration: "none",
                  color: "inherit",
                  justifyContent: "space-between",
                  padding: "10px 0",
                  borderBottom: "1px solid var(--border)",
                }}
                aria-label={`Abrir área ${area.label}`}
              >
                <div>
                  <strong>{area.label}</strong>
                  {area.blurb ? <div className="muted">{area.blurb}</div> : null}
                </div>
                <span className="muted" aria-hidden="true">
                  →
                </span>
              </Link>
            ))}
          </div>
        </section>
        <section className="panel">
          <h2>Capacidades do sistema</h2>
          <MetricWithDenominator
            label="Disponíveis"
            value={data.capabilities.available}
            denominator={data.capabilities.total}
          />
          <p className="muted" style={{ marginTop: 12 }}>
            Capabilities avançadas indisponíveis não são tarefas comerciais do dia — ficam em{" "}
            <Link to="/actions">Avançado</Link>.
          </p>
        </section>
      </div>
    </div>
  );
}
