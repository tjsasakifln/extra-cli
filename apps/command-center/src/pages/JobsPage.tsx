import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { HumanStatusExplanation } from "../components/HumanStatusExplanation";
import { SkeletonState } from "../components/SkeletonState";
import { StatusBadge } from "../components/StatusBadge";

export function JobsPage() {
  const q = useQuery({ queryKey: ["jobs"], queryFn: client.jobs, refetchInterval: 4000 });

  return (
    <div>
      <header className="page-header">
        <h1>Atividades em andamento</h1>
        <p>
          Tudo que você disparou pelo painel: situação, explicação em português e atalho para os resultados.
        </p>
      </header>
      {q.isLoading ? <SkeletonState /> : null}
      {!q.isLoading && (q.data?.jobs.length || 0) === 0 ? (
        <EmptyState title="Nenhuma atividade ainda">
          <Link to="/actions">Escolher uma ação para executar</Link>
        </EmptyState>
      ) : (
        <div className="table-wrap panel" style={{ padding: 0 }}>
          <table className="data">
            <thead>
              <tr>
                <th>O que rodou</th>
                <th>Situação</th>
                <th>Explicação</th>
                <th>Quando</th>
              </tr>
            </thead>
            <tbody>
              {(q.data?.jobs || []).map((j) => (
                <tr key={j.job_id}>
                  <td>
                    <Link to={`/jobs/${j.job_id}`}>{j.action}</Link>
                  </td>
                  <td>
                    <StatusBadge state={j.status} attention={j.attention} />
                  </td>
                  <td>
                    <HumanStatusExplanation
                      code={j.technical_code || j.status}
                      message={j.human_message}
                      nextAction={j.next_action}
                    />
                  </td>
                  <td>{j.created_at ? new Date(j.created_at).toLocaleString("pt-BR") : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
