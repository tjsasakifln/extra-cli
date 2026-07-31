import { Link } from "react-router-dom";
import { DataTable } from "./DataTable";
import { EmptyState } from "./EmptyState";

type ArtifactPayload = {
  kind?: string;
  path?: string;
  name?: string;
  size_bytes?: number;
  message?: string;
  downloadable?: boolean;
  text?: string;
  data?: unknown;
  rows?: Array<Record<string, unknown>>;
  fieldnames?: string[];
  table?: {
    columns: string[];
    rows: Array<Record<string, unknown>>;
    total_rows?: number;
    sampled?: number;
    source_key?: string | null;
  };
  summary?: Record<string, unknown>;
  truncated?: boolean;
};

/** Renders artifacts as tables/summaries first — logs/raw JSON are secondary. */
export function ArtifactViewer({ artifact }: { artifact: ArtifactPayload }) {
  const kind = String(artifact.kind || "");
  const downloadHref = artifact.path
    ? `/api/artifacts/download?path=${encodeURIComponent(artifact.path)}`
    : null;

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <div className="muted" style={{ fontSize: "0.82rem" }}>
            {kind.toUpperCase()} · {(artifact.size_bytes ?? 0).toLocaleString("pt-BR")} bytes
            {artifact.truncated ? " · amostra truncada" : ""}
          </div>
          <div className="mono" style={{ fontSize: "0.85rem", wordBreak: "break-all" }}>
            {artifact.name || artifact.path}
          </div>
        </div>
        {downloadHref ? (
          <a className="btn btn-primary" href={downloadHref}>
            Baixar arquivo
          </a>
        ) : null}
      </div>

      {artifact.summary && Object.keys(artifact.summary).length > 0 ? (
        <div className="summary-grid">
          {Object.entries(artifact.summary).map(([k, v]) => (
            <div className="summary-chip" key={k}>
              <span className="muted">{prettyKey(k)}</span>
              <strong>{String(v)}</strong>
            </div>
          ))}
        </div>
      ) : null}

      {artifact.table ? (
        <div>
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>Tabela</h3>
            <span className="muted" style={{ fontSize: "0.82rem" }}>
              {artifact.table.sampled ?? artifact.table.rows.length}
              {artifact.table.total_rows != null
                ? ` de ${artifact.table.total_rows}`
                : ""}{" "}
              linhas
              {artifact.table.source_key ? ` · campo “${artifact.table.source_key}”` : ""}
            </span>
          </div>
          <DataTable columns={artifact.table.columns} rows={artifact.table.rows} />
        </div>
      ) : null}

      {(kind === "csv" || kind === "jsonl") && artifact.rows ? (
        artifact.rows.length === 0 ? (
          <EmptyState title="Sem linhas na amostra" />
        ) : (
          <DataTable
            columns={
              artifact.fieldnames?.length
                ? artifact.fieldnames
                : Object.keys(artifact.rows[0] || {})
            }
            rows={artifact.rows}
          />
        )
      ) : null}

      {kind === "markdown" || kind === "text" ? (
        <pre className="doc-prose">{String(artifact.text || "")}</pre>
      ) : null}

      {kind === "json" && !artifact.table ? (
        <details className="tech-details">
          <summary>Ver JSON completo (avançado)</summary>
          <pre className="log-stream">{JSON.stringify(artifact.data, null, 2)}</pre>
        </details>
      ) : null}

      {kind === "json" && artifact.table ? (
        <details className="tech-details">
          <summary>Ver JSON bruto (avançado)</summary>
          <pre className="log-stream">{JSON.stringify(artifact.data, null, 2)}</pre>
        </details>
      ) : null}

      {kind === "binary" ? (
        <p>
          {artifact.message || "Arquivo binário."}{" "}
          {downloadHref ? <a href={downloadHref}>Baixar para abrir no Excel/PDF.</a> : null}
        </p>
      ) : null}

      {!["json", "csv", "jsonl", "markdown", "text", "binary"].includes(kind) ? (
        <p>{String(artifact.message || "Visualização não disponível para este tipo.")}</p>
      ) : null}
    </div>
  );
}

function prettyKey(k: string) {
  return k.replace(/_/g, " ");
}

export function ArtifactLinkList({
  paths,
}: {
  paths: string[];
}) {
  if (!paths.length) return <p className="muted">Nenhum resultado anexado ainda.</p>;
  return (
    <ul className="result-list">
      {paths.map((p) => (
        <li key={p}>
          <Link to={`/results?path=${encodeURIComponent(p)}`}>{p.split(/[/\\]/).pop() || p}</Link>
          <span className="muted mono" style={{ fontSize: "0.75rem", marginLeft: 8 }}>
            {p}
          </span>
        </li>
      ))}
    </ul>
  );
}
