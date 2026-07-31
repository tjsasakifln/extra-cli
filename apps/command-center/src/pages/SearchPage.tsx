import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { SkeletonState } from "../components/SkeletonState";

export function SearchPage() {
  const [params] = useSearchParams();
  const q = params.get("q") || "";
  const search = useQuery({
    queryKey: ["search", q],
    queryFn: () => client.search(q),
    enabled: q.trim().length >= 2,
  });

  return (
    <div>
      <header className="page-header">
        <h1>Busca</h1>
        <p>
          Resultados para <span className="mono">{q || "—"}</span>
        </p>
      </header>
      {search.isLoading ? <SkeletonState /> : null}
      {!search.isLoading && (search.data?.results.length || 0) === 0 ? (
        <EmptyState title="Nenhum resultado">Tente capability, job id ou nome de artifact.</EmptyState>
      ) : (
        <ul className="stack">
          {(search.data?.results || []).map((r) => (
            <li key={`${r.type}-${r.id}`} className="panel" style={{ marginTop: 0 }}>
              <div className="muted" style={{ fontSize: "0.78rem" }}>
                {r.type}
              </div>
              <Link to={r.href}>{r.label}</Link>
              <div className="muted">{r.detail}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
