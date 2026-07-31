import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { BrandLogo } from "../components/BrandLogo";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { MetricWithDenominator } from "../components/MetricWithDenominator";
import { SkeletonState } from "../components/SkeletonState";
import { StatusBadge } from "../components/StatusBadge";
import { HumanStatusExplanation } from "../components/HumanStatusExplanation";

export function HomePage() {
  const q = useQuery({ queryKey: ["overview"], queryFn: client.overview, refetchInterval: 10000 });

  if (q.isLoading) return <SkeletonState lines={8} />;
  if (q.isError) return <ErrorState title="Não foi possível carregar o painel" error={(q.error as Error).message} />;

  const data = q.data as {
    headline: string;
    attention: Array<{ kind: string; title: string; detail?: string; href: string }>;
    capabilities: { total: number; available: number; unavailable: number };
    jobs: { recent: Array<Record<string, unknown>>; counts: Record<string, number> };
    quick_actions: Array<{ id: string; label: string; href: string; blurb?: string }>;
    areas: Array<{ id: string; label: string; href: string; blurb?: string }>;
    health: { sha: string; env: Record<string, string>; profile: string };
  };

  return (
    <div>
      <header className="page-header">
        <div className="row" style={{ gap: 16, marginBottom: 8 }}>
          <BrandLogo variant="auto" height={36} />
        </div>
        <h1>O que fazer agora?</h1>
        <p>
          Este é o seu centro de operação da consultoria: gerar listas, abrir resultados em tabela, revisar o que
          precisa de decisão humana e acompanhar o que está rodando — tudo com um clique, sem terminal.
        </p>
      </header>

      <section className="hero-panel" aria-labelledby="attention-title">
        <h2 id="attention-title" style={{ marginTop: 0 }}>
          {data.headline}
        </h2>
        {data.attention.length === 0 ? (
          <EmptyState title="Nada urgente no momento">
            Use as ações abaixo para gerar uma lista ou abrir resultados recentes.
          </EmptyState>
        ) : (
          <div>
            {data.attention.slice(0, 6).map((item, idx) => (
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
                <Link className="btn btn-primary" to={item.href}>
                  Abrir
                </Link>
              </div>
            ))}
          </div>
        )}
      </section>

      <section style={{ marginTop: 20 }}>
        <h2 style={{ marginBottom: 12 }}>Ações principais</h2>
        <div className="grid-actions">
          {data.quick_actions.map((a) => (
            <Link key={a.id} className="action-card" to={a.href}>
              <strong>{a.label}</strong>
              <span className="muted">{a.blurb || "Abrir fluxo"}</span>
              <span className="btn" style={{ alignSelf: "flex-start", pointerEvents: "none" }}>
                Continuar
              </span>
            </Link>
          ))}
        </div>
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
              >
                <div>
                  <strong>{area.label}</strong>
                  {area.blurb ? <div className="muted">{area.blurb}</div> : null}
                </div>
                <span className="btn">Abrir</span>
              </Link>
            ))}
          </div>
        </section>
        <section className="panel">
          <h2>Situação do ambiente</h2>
          <div className="stack">
            <MetricWithDenominator
              label="Ações disponíveis neste computador"
              value={data.capabilities.available}
              denominator={data.capabilities.total}
              unitLabel="prontas de total descobertas"
            />
            <MetricWithDenominator
              label="Atividades em andamento"
              value={data.jobs.counts.active || 0}
              denominator={data.jobs.counts.total || 0}
              unitLabel="ativas de recentes"
            />
            <div>
              <div className="muted" style={{ fontSize: "0.82rem", fontWeight: 600 }}>
                Conexões (sem exibir senhas)
              </div>
              <ul>
                {Object.entries(data.health.env || {}).map(([k, v]) => (
                  <li key={k}>
                    {friendlyEnv(k)}: <strong>{friendlyPresence(v)}</strong>
                  </li>
                ))}
                <li>
                  Perfil da Extra: <strong>{data.health.profile}</strong>
                </li>
              </ul>
            </div>
          </div>
        </section>
      </div>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>Atividade recente</h2>
          <Link to="/jobs">Ver todas</Link>
        </div>
        {data.jobs.recent.length === 0 ? (
          <EmptyState title="Nenhuma atividade ainda">
            Escolha uma ação principal acima — por exemplo, validar o perfil ou gerar a lista de fornecedores.
          </EmptyState>
        ) : (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table className="data">
              <thead>
                <tr>
                  <th>O que rodou</th>
                  <th>Situação</th>
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
                      <Link to={`/jobs/${j.job_id}`}>Abrir</Link>
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

function friendlyEnv(key: string): string {
  if (key.includes("DATALAKE") || key.includes("DATABASE")) return "Banco de dados local";
  if (key.includes("OPENAI")) return "Assistente de IA (chave)";
  return key;
}

function friendlyPresence(v: string): string {
  const map: Record<string, string> = {
    configurada: "configurada",
    ausente: "ainda não configurada",
    inválida: "inválida — revisar",
    "não testada": "presente (não testada agora)",
  };
  return map[v] || v;
}
