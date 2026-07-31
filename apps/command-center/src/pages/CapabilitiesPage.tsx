import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { CapabilityCard } from "../components/CapabilityCard";
import { EmptyState } from "../components/EmptyState";
import { SkeletonState } from "../components/SkeletonState";

export function CapabilitiesPage() {
  const q = useQuery({ queryKey: ["capabilities"], queryFn: () => client.capabilities() });
  const [filter, setFilter] = useState("");
  const [onlyAvailable, setOnlyAvailable] = useState(false);

  const items = useMemo(() => {
    let list = q.data?.capabilities || [];
    if (onlyAvailable) list = list.filter((c) => c.availability === "available");
    if (filter) {
      const f = filter.toLowerCase();
      list = list.filter(
        (c) =>
          c.id.toLowerCase().includes(f) ||
          c.name.toLowerCase().includes(f) ||
          c.description.toLowerCase().includes(f) ||
          c.category.toLowerCase().includes(f),
      );
    }
    return list;
  }, [q.data, filter, onlyAvailable]);

  return (
    <div>
      <header className="page-header">
        <h1>Capabilities</h1>
        <p>
          Registro declarativo no backend. A UI nunca monta comandos — apenas envia capability id +
          parâmetros validados.
        </p>
      </header>
      <div className="panel row" style={{ marginBottom: 16 }}>
        <div className="field" style={{ flex: 1, marginBottom: 0 }}>
          <label htmlFor="cap-filter">Filtrar</label>
          <input id="cap-filter" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
        <label className="row" style={{ marginTop: 22 }}>
          <input type="checkbox" checked={onlyAvailable} onChange={(e) => setOnlyAvailable(e.target.checked)} />
          Somente disponíveis
        </label>
      </div>
      {q.isLoading ? <SkeletonState /> : null}
      {!q.isLoading && items.length === 0 ? <EmptyState title="Nenhuma capability encontrada" /> : null}
      <div className="grid-2">
        {items.map((cap) => (
          <CapabilityCard key={cap.id} cap={cap} />
        ))}
      </div>
    </div>
  );
}
