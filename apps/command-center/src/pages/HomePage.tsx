import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { MetricWithDenominator } from "../components/MetricWithDenominator";
import { SkeletonState } from "../components/SkeletonState";
import { StatusBadge } from "../components/StatusBadge";
import { HumanStatusExplanation } from "../components/HumanStatusExplanation";

export function HomePage() {
  const q = useQuery({ queryKey: ["overview"], queryFn: client.overview, refetchInterval: 10000 });

  if (q.isLoading) return <SkeletonState lines={8} />;
  if (q.isError) return <ErrorState title="Não foi possível carregar a visão geral" error={(q.error as Error).message} />;

  const data = q.data as {
    headline: string;
    attention: Array<{ kind: string; title: string; detail?: string; href: string }>;
    capabilities: { total: number; available: number; unavailable: number };
    jobs: { recent: Array<Record<string, unknown>>; counts: Record<string, number> };
    quick_actions: Array<{ id: string; label: string; href: string }>;
    areas: Array<{ id: string; label: string; href: string }>;
    health: { sha: string; env: Record<string, string>; profile: string };
  };

  return (
    <div>
      <header className="page-header">
        <h1>Visão Geral</h1>
        <p>
          Centro de comando local sobre o extra-cli. A primeira dobra responde: o que precisa da sua
          atenção agora — sem inventar métricas e sem esconder bloqueios.
        </p>
      </header>

      <section className="panel" aria-labelledby="attention-title">
        <h2 id="attention-title">{data.headline}</h2>
        {data.attention.length === 0 ? (
          <EmptyState title="Nada urgente no momento">
            As áreas estão quietas. Use as ações rápidas se quiser iniciar um fluxo.
          </EmptyState>
        ) : (
          <div>
            {data.attention.map((item, idx) => (
              <div className="attention-item" key={`${item.title}-${idx}`}>
                <StatusBadge
                  attention={
                    item.kind.includes("missing")
                      ? "no_data"
                      : item.kind.includes("running")
                        ? "running"
                        : "attention"
                  }
                />
                <div>
                  <strong>{item.title}</strong>
                  {item.detail ? <div className="muted">{item.detail}</div> : null}
                </div>
                <Link className="btn" to={item.href}>
                  Abrir
                </Link>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="grid-2" style={{ marginTop: 16 }}>
        <section className="panel">
          <h2>Ações rápidas</h2>
          <div className="stack">
            {data.quick_actions.map((a) => (
              <div className="row" key={a.id} style={{ justifyContent: "space-between" }}>
                <div>
                  <div>{a.label}</div>
                  <div className="mono muted" style={{ fontSize: "0.78rem" }}>
                    {a.id}
                  </div>
                </div>
                <Link className="btn btn-primary" to={a.href}>
                  Ir
                </Link>
              </div>
            ))}
          </div>
        </section>
        <section className="panel">
          <h2>Estado do sistema</h2>
          <div className="stack">
            <MetricWithDenominator
              label="Capabilities disponíveis"
              value={data.capabilities.available}
              denominator={data.capabilities.total}
              unitLabel="descobertas dinamicamente nesta versão"
            />
            <MetricWithDenominator
              label="Jobs ativos"
              value={data.jobs.counts.active || 0}
              denominator={data.jobs.counts.total || 0}
              unitLabel="ativos de total recente"
            />
            <div>
              <div className="muted" style={{ fontSize: "0.82rem", fontWeight: 600 }}>
                Ambiente sensível (sem valores)
              </div>
              <ul>
                {Object.entries(data.health.env || {}).map(([k, v]) => (
                  <li key={k}>
                    <span className="mono">{k}</span>: {v}
                  </li>
                ))}
                <li>
                  Perfil Extra: {data.health.profile}
                </li>
              </ul>
            </div>
          </div>
        </section>
      </div>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Áreas</h2>
        <div className="grid-3">
          {data.areas.map((area) => (
            <Link key={area.id} className="panel" style={{ marginTop: 0, textDecoration: "none", color: "inherit" }} to={area.href}>
              <strong>{area.label}</strong>
              <div className="muted" style={{ marginTop: 6 }}>
                Abrir área operacional
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Atividade recente</h2>
        {data.jobs.recent.length === 0 ? (
          <EmptyState title="Nenhum job ainda">
            Execute a fixture segura em Capabilities para validar o runner.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Ação</th>
                  <th>Status</th>
                  <th>Explicação</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.jobs.recent.map((j) => (
                  <tr key={String(j.job_id)}>
                    <td>{String(j.action)}</td>
                    <td>
                      <StatusBadge state={String(j.status)} attention={String(j.attention || "")} />
                    </td>
                    <td>
                      <HumanStatusExplanation
                        code={String(j.technical_code || j.status)}
                        message={String(j.human_message || "")}
                        nextAction={j.next_action ? String(j.next_action) : null}
                      />
                    </td>
                    <td>
                      <Link to={`/jobs/${j.job_id}`}>Detalhe</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
