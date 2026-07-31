import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { ArtifactViewer } from "../components/ArtifactViewer";
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
    return <ArtifactViewer artifact={one.data as Record<string, unknown>} />;
  }, [one.data]);

  return (
    <div>
      <header className="page-header">
        <h1>Resultados e relatórios</h1>
        <p>
          Aqui você abre o que foi gerado: listas em tabela, resumos e arquivos para baixar no Excel. Nada de
          digitar comando — clique no resultado.
        </p>
      </header>
      {path ? (
        <section className="panel">
          <p className="muted" style={{ marginTop: 0 }}>
            <Link to="/results">← Voltar à lista</Link>
          </p>
          {one.isLoading ? <SkeletonState /> : null}
          {one.isError ? (
            <ErrorState title="Não foi possível abrir este resultado" error={(one.error as Error).message} />
          ) : null}
          {body}
        </section>
      ) : (
        <section className="panel">
          <h2>Mais recentes</h2>
          {recent.isLoading ? <SkeletonState /> : null}
          {(recent.data?.recent || []).length === 0 ? (
            <EmptyState title="Ainda não há resultados salvos">
              Depois de rodar uma ação (lista de fornecedores, ciclo semanal, documentos), os arquivos
              aparecem aqui automaticamente.
            </EmptyState>
          ) : (
            <ul className="result-list">
              {(recent.data?.recent || []).map((a) => (
                <li key={String(a.path)}>
                  <Link to={`/results?path=${encodeURIComponent(String(a.path))}`}>
                    <strong>{String(a.name || a.path)}</strong>
                  </Link>
                  <span className="muted">
                    {" "}
                    · {String(a.suffix || "").replace(".", "").toUpperCase() || "arquivo"} ·{" "}
                    {Number(a.size_bytes || 0).toLocaleString("pt-BR")} bytes
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
