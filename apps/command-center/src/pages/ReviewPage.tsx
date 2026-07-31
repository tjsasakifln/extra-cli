import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { DecisionPanel } from "../components/DecisionPanel";
import { EmptyState } from "../components/EmptyState";

export function ReviewPage() {
  const decisions = useQuery({ queryKey: ["decisions"], queryFn: client.decisions });

  return (
    <div>
      <header className="page-header">
        <h1>Revisão humana</h1>
        <p>
          Decisões ACCEPT / REJECT / DEFER com confirmação forte para ações sensíveis. O sistema nunca decide por
          você e não envia outreach.
        </p>
      </header>

      <DecisionPanel
        itemId="review-demo-local"
        title="Incluir item de exemplo na fila manual de prospecção"
        evidence="Evidence paths e scores viriam do artifact da capability correspondente."
        limitations="Isto não autoriza contato automático nem aceite de item DOD."
        risks="Falso positivo comercial; classificação jurídica incompleta."
      />

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
