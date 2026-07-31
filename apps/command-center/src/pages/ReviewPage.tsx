import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { client } from "../api/client";
import { DecisionPanel } from "../components/DecisionPanel";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { SkeletonState } from "../components/SkeletonState";

export function ReviewPage() {
  const qc = useQueryClient();
  const reviews = useQuery({
    queryKey: ["reviews", "pending"],
    queryFn: () => client.reviews("pending"),
    refetchInterval: 8000,
  });
  const decisions = useQuery({ queryKey: ["decisions"], queryFn: client.decisions });

  return (
    <div>
      <header className="page-header">
        <h1>Revisão humana</h1>
        <p>
          Fila real de itens pendentes (jobs em bloqueio humano e enfileiramentos explícitos). ACCEPT /
          REJECT / DEFER com confirmação forte — o sistema nunca decide por você e não envia outreach.
        </p>
      </header>

      <section className="panel" aria-labelledby="queue-title">
        <h2 id="queue-title">Fila pendente</h2>
        {reviews.isLoading ? <SkeletonState /> : null}
        {reviews.isError ? (
          <ErrorState title="Falha ao carregar a fila" error={(reviews.error as Error).message} />
        ) : null}
        {!reviews.isLoading && (reviews.data?.reviews.length || 0) === 0 ? (
          <EmptyState title="Nenhuma revisão humana pendente">
            Itens aparecem aqui quando um job termina em bloqueio humano (ex.: labels insuficientes) ou
            quando um pacote é enfileirado explicitamente. Isso não é um demo fixo.
          </EmptyState>
        ) : (
          <div className="stack">
            {(reviews.data?.reviews || []).map((item) => (
              <div key={String(item.id)} className="panel" style={{ marginTop: 0, boxShadow: "none" }}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <strong>{String(item.title)}</strong>
                  <span className="mono muted" style={{ fontSize: "0.78rem" }}>
                    {String(item.id)}
                  </span>
                </div>
                <p className="muted" style={{ marginBottom: 8 }}>
                  Fonte: {String(item.source)}
                  {item.job_id ? (
                    <>
                      {" "}
                      · Job: <Link to={`/jobs/${String(item.job_id)}`}>{String(item.job_id)}</Link>
                    </>
                  ) : null}
                </p>
                <DecisionPanel
                  itemId={String(item.id)}
                  title={String(item.title)}
                  evidence={String(item.evidence)}
                  limitations={String(item.limitations)}
                  risks={String(item.risks)}
                  onDecided={() => {
                    void qc.invalidateQueries({ queryKey: ["reviews"] });
                    void qc.invalidateQueries({ queryKey: ["decisions"] });
                  }}
                />
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Histórico local de decisões</h2>
        {(decisions.data?.decisions || []).length === 0 ? (
          <EmptyState title="Nenhuma decisão registrada ainda" />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Quando</th>
                  <th>Item</th>
                  <th>Decisão</th>
                  <th>Ator</th>
                </tr>
              </thead>
              <tbody>
                {(decisions.data?.decisions || []).map((d) => (
                  <tr key={String(d.id)}>
                    <td className="mono">{String(d.ts)}</td>
                    <td>{String(d.item_id)}</td>
                    <td>{String(d.decision)}</td>
                    <td>{String(d.actor)}</td>
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
