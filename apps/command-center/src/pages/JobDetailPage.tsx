import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { client } from "../api/client";
import { ArtifactLinkList, ArtifactViewer } from "../components/ArtifactViewer";
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
  const [previewPath, setPreviewPath] = useState<string | null>(null);

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

  const job = q.data?.job;
  const firstArtifact = job?.artifacts?.[0] || null;
  useEffect(() => {
    if (firstArtifact && !previewPath) setPreviewPath(firstArtifact);
  }, [firstArtifact, previewPath]);

  const preview = useQuery({
    queryKey: ["artifact", previewPath],
    queryFn: () => client.artifact(previewPath || ""),
    enabled: Boolean(previewPath),
  });

  if (q.isLoading) return <SkeletonState />;
  if (q.isError || !job) {
    return <ErrorState title="Atividade não encontrada" error={(q.error as Error)?.message} />;
  }
  const running = ["QUEUED", "VALIDATING", "RUNNING", "CANCELLING"].includes(job.status);
  const done = !running;

  return (
    <div>
      <header className="page-header">
        <p className="muted">
          <Link to="/jobs">Atividades</Link> / {job.action}
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
          {done ? (
            <Link className="btn" to="/results">
              Ir para resultados
            </Link>
          ) : null}
          {job.status === "BLOCKED_HUMAN" ? (
            <Link className="btn btn-primary" to="/review">
              Ir para revisões
            </Link>
          ) : null}
        </div>
      </header>

      <div className="grid-2">
        <section className="panel">
          <h2>Situação</h2>
          <HumanStatusExplanation
            code={job.technical_code || job.status}
            message={job.human_message}
            nextAction={job.next_action}
          />
          <ul>
            <li>
              Início: {job.started_at ? new Date(job.started_at).toLocaleString("pt-BR") : "—"}
            </li>
            <li>Fim: {job.finished_at ? new Date(job.finished_at).toLocaleString("pt-BR") : "—"}</li>
            <li>
              Duração:{" "}
              {job.duration_ms != null ? `${Math.round(job.duration_ms / 1000)} s` : "—"}
            </li>
          </ul>
          {cancelError ? <p role="alert">{cancelError}</p> : null}
        </section>
        <section className="panel">
          <h2>Resultados desta atividade</h2>
          <ArtifactLinkList paths={job.artifacts || []} />
          {(job.artifacts || []).length > 0 ? (
            <div className="row" style={{ marginTop: 8 }}>
              {(job.artifacts || []).slice(0, 6).map((a) => (
                <button
                  key={a}
                  type="button"
                  className={`btn ${previewPath === a ? "btn-primary" : ""}`}
                  onClick={() => setPreviewPath(a)}
                >
                  Ver {a.split(/[/\\]/).pop()}
                </button>
              ))}
            </div>
          ) : (
            <p className="muted">
              {running
                ? "Os arquivos aparecem aqui quando a atividade os gerar."
                : "Nenhum arquivo detectado automaticamente — confira Resultados se souber o nome."}
            </p>
          )}
        </section>
      </div>

      {previewPath ? (
        <section className="panel" style={{ marginTop: 16 }}>
          <h2>Pré-visualização</h2>
          {preview.isLoading ? <SkeletonState /> : null}
          {preview.isError ? (
            <p className="muted">Não foi possível pré-visualizar. Use “Baixar” em Resultados.</p>
          ) : null}
          {preview.data ? <ArtifactViewer artifact={preview.data as Record<string, unknown>} /> : null}
        </section>
      ) : null}

      <details className="tech-details" style={{ marginTop: 16 }} open={running}>
        <summary>{running ? "Acompanhamento ao vivo" : "Registro detalhado (avançado)"}</summary>
        <LogStream lines={lines} />
        <details className="tech-details" style={{ marginTop: 12 }}>
          <summary>Comando equivalente (para suporte técnico)</summary>
          <pre className="log-stream" style={{ maxHeight: 120 }}>
            {(job.canonical_command || []).join(" ")}
          </pre>
        </details>
      </details>
    </div>
  );
}
