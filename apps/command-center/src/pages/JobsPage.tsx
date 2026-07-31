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
        <h1>Jobs</h1>
        <p>Execuções allowlisted com estados normalizados, logs e artefatos.</p>
      </header>
      {q.isLoading ? <SkeletonState /> : null}
      {!q.isLoading && (q.data?.jobs.length || 0) === 0 ? (
        <EmptyState title="Nenhum job registrado">
          <Link to="/capabilities/cc.fixture.echo">Rodar fixture segura</Link>
        </EmptyState>
      ) : (
        <div className="table-wrap panel" style={{ padding: 0 }}>
          <table className="data">
            <thead>
              <tr>
                <th>Ação</th>
                <th>Capability</th>
                <th>Status</th>
                <th>Explicação</th>
                <th>Criado</th>
              </tr>
            </thead>
            <tbody>
              {(q.data?.jobs || []).map((j) => (
                <tr key={j.job_id}>
                  <td>
                    <Link to={`/jobs/${j.job_id}`}>{j.action}</Link>
                  </td>
                  <td className="mono">{j.capability_id}</td>
                  <td>
                    <StatusBadge state={j.status} attention={j.attention} />
                  </td>
                  <td>
                    <HumanStatusExplanation code={j.technical_code || j.status} message={j.human_message} nextAction={j.next_action} />
                  </td>
                  <td className="mono">{j.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
