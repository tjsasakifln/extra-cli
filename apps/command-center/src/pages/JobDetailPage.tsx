import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { client } from "../api/client";
import { ErrorState } from "../components/ErrorState";
import { HumanStatusExplanation } from "../components/HumanStatusExplanation";
import { LogStream } from "../components/LogStream";
import { SkeletonState } from "../components/SkeletonState";
import { StatusBadge } from "../components/StatusBadge";

export function JobDetailPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["job", id], queryFn: () => client.job(id), refetchInterval: 3000 });
  const [lines, setLines] = useState<Array<{ stream?: string; message: string }>>([]);
  const [cancelError, setCancelError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    const es = new EventSource(`/api/jobs/${encodeURIComponent(id)}/events`);
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === "log") {
          setLines((prev) => [...prev, { stream: data.stream, message: data.message }]);
        }
        if (data.type === "status") {
          void qc.invalidateQueries({ queryKey: ["job", id] });
        }
      } catch {
        /* ignore */
      }
    };
    es.addEventListener("end", () => es.close());
    return () => es.close();
  }, [id, qc]);

  if (q.isLoading) return <SkeletonState />;
  if (q.isError || !q.data) return <ErrorState title="Job não encontrado" error={(q.error as Error)?.message} />;
  const job = q.data.job;
  const running = ["QUEUED", "VALIDATING", "RUNNING", "CANCELLING"].includes(job.status);

  return (
    <div>
      <header className="page-header">
        <p className="muted">
          <Link to="/jobs">Jobs</Link> / <span className="mono">{job.job_id}</span>
        </p>
        <h1>{job.action}</h1>
        <div className="row">
          <StatusBadge state={job.status} attention={job.attention} />
          {running ? (
            <button
              type="button"
              className="btn btn-danger"
              onClick={() => {
                void client
                  .cancelJob(job.job_id)
                  .then(() => qc.invalidateQueries({ queryKey: ["job", id] }))
                  .catch((e) => setCancelError(e instanceof Error ? e.message : String(e)));
              }}
            >
              Cancelar
            </button>
          ) : null}
        </div>
      </header>

      <div className="grid-2">
        <section className="panel">
          <h2>Status</h2>
          <HumanStatusExplanation
            code={job.technical_code || job.status}
            message={job.human_message}
            nextAction={job.next_action}
          />
          <ul>
            <li>Capability: <span className="mono">{job.capability_id}</span></li>
            <li>Exit code: {job.exit_code ?? "—"}</li>
            <li>SHA: <span className="mono">{job.code_sha || "—"}</span></li>
            <li>Início: {job.started_at || "—"}</li>
            <li>Fim: {job.finished_at || "—"}</li>
            <li>Duração: {job.duration_ms != null ? `${job.duration_ms} ms` : "—"}</li>
          </ul>
          {cancelError ? <p role="alert">{cancelError}</p> : null}
        </section>
        <section className="panel">
          <h2>Comando canônico equivalente</h2>
          <pre className="log-stream" style={{ maxHeight: 180 }}>
            {(job.canonical_command || []).join(" ")}
          </pre>
          <h3>Artefatos</h3>
          {(job.artifacts || []).length === 0 ? (
            <p className="muted">Nenhum caminho de artifact detectado ainda.</p>
          ) : (
            <ul>
              {job.artifacts.map((a) => (
                <li key={a}>
                  <Link to={`/artifacts?path=${encodeURIComponent(a)}`}>{a}</Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div style={{ marginTop: 16 }}>
        <LogStream lines={lines} />
      </div>
    </div>
  );
}
