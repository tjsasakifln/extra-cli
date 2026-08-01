import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { CapabilityCard } from "../components/CapabilityCard";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { SkeletonState } from "../components/SkeletonState";

const CAT_LABEL: Record<string, string> = {
  extra: "Oportunidades Extra",
  confenge_suppliers: "Fornecedores CONFENGE",
  confenge_agencies: "Órgãos públicos",
  process_documents: "Documentos",
  ops: "Sistema",
  dod: "Evidências",
};

export function CapabilitiesPage() {
  const q = useQuery({ queryKey: ["capabilities"], queryFn: () => client.capabilities() });
  const [filter, setFilter] = useState("");
  const [cat, setCat] = useState<string>("all");

  const items = useMemo(() => {
    const list = q.data?.capabilities || [];
    return list.filter((c) => {
      if (cat !== "all" && c.category !== cat) return false;
      if (!filter.trim()) return true;
      const blob = `${c.name} ${c.description} ${c.id}`.toLowerCase();
      return blob.includes(filter.trim().toLowerCase());
    });
  }, [q.data, filter, cat]);

  const categories = useMemo(() => {
    const s = new Set((q.data?.capabilities || []).map((c) => c.category));
    return Array.from(s).sort();
  }, [q.data]);

  return (
    <div>
      <header className="page-header">
        <h1>Todas as ações</h1>
        <p>
          Cada botão abaixo corresponde a algo que você faria no dia a dia da consultoria. Clique, preencha se
          pedido, e acompanhe o resultado em tabela — sem linha de comando.
        </p>
      </header>

      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="row">
          <input
            type="search"
            placeholder="Filtrar por nome…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ flex: 1, minWidth: 200, padding: "8px 12px", borderRadius: 8, border: "1px solid var(--border)" }}
          />
          <select value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Filtrar área">
            <option value="all">Todas as áreas</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {CAT_LABEL[c] || c}
              </option>
            ))}
          </select>
        </div>
      </section>

      {q.isLoading ? <SkeletonState /> : null}
      {q.isError ? <ErrorState title="Falha ao listar ações" error={(q.error as Error).message} /> : null}
      {!q.isLoading && items.length === 0 ? <EmptyState title="Nenhuma ação encontrada" /> : null}
      <div className="grid-2">
        {items.map((cap) => (
          <CapabilityCard key={cap.id} cap={cap} />
        ))}
      </div>
    </div>
  );
}
