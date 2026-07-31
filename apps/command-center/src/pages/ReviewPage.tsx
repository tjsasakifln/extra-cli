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
        <h1>Revisões humanas</h1>
        <p>
          Itens que só você pode decidir: aceitar, recusar ou deixar para depois. Cada cartão traz evidências,
          limitações e riscos. O sistema não decide e não envia nada sozinho.
        </p>
      </header>

      <section className="panel" aria-labelledby="queue-title">
        <h2 id="queue-title">Aguardando você</h2>
        {reviews.isLoading ? <SkeletonState /> : null}
        {reviews.isError ? (
          <ErrorState title="Não foi possível carregar a fila" error={(reviews.error as Error).message} />
        ) : null}
        {!reviews.isLoading && (reviews.data?.reviews.length || 0) === 0 ? (
          <EmptyState title="Nada pendente de revisão">
            Quando uma lista ou análise precisar da sua validação, o item aparece aqui com o contexto completo.
          </EmptyState>
        ) : (
          <div className="stack">
            {(reviews.data?.reviews || []).map((item) => (
              <article key={String(item.id)} className="panel" style={{ marginTop: 0 }}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <strong style={{ fontSize: "1.05rem" }}>{String(item.title)}</strong>
                  <span className="muted" style={{ fontSize: "0.82rem" }}>
                    {String(item.source)}
                  </span>
                </div>
                {item.job_id ? (
                  <p className="muted" style={{ marginBottom: 0 }}>
                    Atividade relacionada:{" "}
                    <Link to={`/jobs/${String(item.job_id)}`}>abrir resultados e detalhes</Link>
                  </p>
                ) : null}
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
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Histórico das suas decisões</h2>
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
                  <th>Quem</th>
                </tr>
              </thead>
              <tbody>
                {(decisions.data?.decisions || []).map((d) => (
                  <tr key={String(d.id)}>
                    <td>{d.ts ? new Date(String(d.ts)).toLocaleString("pt-BR") : "—"}</td>
                    <td>{String(d.item_id)}</td>
                    <td>{friendlyDecision(String(d.decision))}</td>
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

function friendlyDecision(d: string): string {
  if (d === "ACCEPT") return "Aceito";
  if (d === "REJECT") return "Recusado";
  if (d === "DEFER") return "Adiado";
  return d;
}
