import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { SkeletonState } from "../components/SkeletonState";

export function ArtifactsPage() {
  const [params] = useSearchParams();
  const path = params.get("path") || "";
  const recent = useQuery({
    queryKey: ["artifacts-recent"],
    queryFn: client.recentArtifacts,
    enabled: !path,
  });
  const one = useQuery({
    queryKey: ["artifact", path],
    queryFn: () => client.artifact(path),
    enabled: Boolean(path),
  });

  const body = useMemo(() => {
    if (!one.data) return null;
    const kind = String(one.data.kind || "");
    if (kind === "json") return <pre className="log-stream">{JSON.stringify(one.data.data, null, 2)}</pre>;
    if (kind === "csv" || kind === "jsonl") {
      const rows = (one.data.rows as Array<Record<string, unknown>>) || [];
      if (!rows.length) return <EmptyState title="Sem linhas na amostra" />;
      const cols = Object.keys(rows[0]);
      return (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                {cols.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  {cols.map((c) => (
                    <td key={c}>{String(r[c] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    if (kind === "markdown" || kind === "text") {
      return <pre className="log-stream">{String(one.data.text || "")}</pre>;
    }
    return <p>{String(one.data.message || "Visualização não embutida.")}</p>;
  }, [one.data]);

  return (
    <div>
      <header className="page-header">
        <h1>Artefatos</h1>
        <p>
          Leitura segura dentro de roots permitidos. HTML arbitrário não é executado; secrets são
          redigidos.
        </p>
      </header>
      {path ? (
        <section className="panel">
          <h2 className="mono" style={{ fontSize: "0.95rem" }}>
            {path}
          </h2>
          {one.isLoading ? <SkeletonState /> : null}
          {one.isError ? <ErrorState title="Falha ao ler artifact" error={(one.error as Error).message} /> : null}
          {body}
          {path ? (
            <p>
              <a href={`/api/artifacts/download?path=${encodeURIComponent(path)}`}>Download</a>
            </p>
          ) : null}
        </section>
      ) : (
        <section className="panel">
          <h2>Recentes</h2>
          {recent.isLoading ? <SkeletonState /> : null}
          {(recent.data?.recent || []).length === 0 ? (
            <EmptyState title="Nenhum artifact recente nas roots permitidas" />
          ) : (
            <ul>
              {(recent.data?.recent || []).map((a) => (
                <li key={String(a.path)}>
                  <a href={`/artifacts?path=${encodeURIComponent(String(a.path))}`}>{String(a.path)}</a>
                  <span className="muted"> · {String(a.size_bytes)} bytes</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
