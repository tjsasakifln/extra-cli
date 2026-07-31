/** Operational table: sort, filter, search, pagination — no heavy grid dependency. */

import { useMemo, useState } from "react";

export function DataTable({
  columns,
  rows,
  caption,
  maxHeight = 420,
  pageSize = 25,
  selectable = false,
  onSelectionChange,
}: {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  caption?: string;
  maxHeight?: number;
  pageSize?: number;
  selectable?: boolean;
  onSelectionChange?: (selected: number[]) => void;
}) {
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [query, setQuery] = useState("");
  const [colFilters, setColFilters] = useState<Record<string, string>>({});
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const label = (col: string) =>
    col
      .replace(/_/g, " ")
      .replace(/\bcnpj\b/gi, "CNPJ")
      .replace(/\buf\b/gi, "UF");

  const filtered = useMemo(() => {
    let out = rows.map((r, i) => ({ r, i }));
    const q = query.trim().toLowerCase();
    if (q) {
      out = out.filter(({ r }) =>
        columns.some((c) => String(r[c] ?? "").toLowerCase().includes(q)),
      );
    }
    for (const [col, val] of Object.entries(colFilters)) {
      const f = val.trim().toLowerCase();
      if (!f) continue;
      out = out.filter(({ r }) => String(r[col] ?? "").toLowerCase().includes(f));
    }
    if (sortCol) {
      out = [...out].sort((a, b) => {
        const av = a.r[sortCol];
        const bv = b.r[sortCol];
        const an = typeof av === "number" ? av : Number(av);
        const bn = typeof bv === "number" ? bv : Number(bv);
        let cmp = 0;
        if (Number.isFinite(an) && Number.isFinite(bn)) cmp = an - bn;
        else cmp = String(av ?? "").localeCompare(String(bv ?? ""), "pt-BR", { sensitivity: "base" });
        return sortDir === "asc" ? cmp : -cmp;
      });
    }
    return out;
  }, [rows, columns, query, colFilters, sortCol, sortDir]);

  const total = filtered.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, pageCount - 1);
  const pageRows = filtered.slice(safePage * pageSize, safePage * pageSize + pageSize);

  const toggleSort = (col: string) => {
    if (sortCol === col) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortCol(col);
      setSortDir("asc");
    }
  };

  const toggleRow = (origIndex: number) => {
    const next = new Set(selected);
    if (next.has(origIndex)) next.delete(origIndex);
    else next.add(origIndex);
    setSelected(next);
    onSelectionChange?.(Array.from(next));
  };

  if (!columns.length) {
    return <p className="muted">Nenhuma coluna disponível.</p>;
  }
  if (!rows.length) {
    return <p className="muted">Nenhuma linha para exibir.</p>;
  }

  return (
    <div className="stack">
      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        <label className="field" style={{ flex: 1, minWidth: 160, margin: 0 }}>
          <span className="sr-only">Buscar na tabela</span>
          <input
            type="search"
            placeholder="Buscar…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
            aria-label="Buscar na tabela"
          />
        </label>
        <span className="muted" style={{ fontSize: "0.82rem" }}>
          {total.toLocaleString("pt-BR")} linha(s)
          {selected.size > 0 ? ` · ${selected.size} selecionada(s)` : ""}
        </span>
      </div>
      <div className="table-wrap" style={{ maxHeight }}>
        <table className="data">
          {caption ? <caption className="sr-only">{caption}</caption> : null}
          <thead>
            <tr>
              {selectable ? <th scope="col">Sel.</th> : null}
              {columns.map((c) => (
                <th key={c} scope="col">
                  <button type="button" className="btn" style={{ padding: "2px 6px" }} onClick={() => toggleSort(c)}>
                    {label(c)}
                    {sortCol === c ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
                  </button>
                  <input
                    type="search"
                    placeholder="Filtrar"
                    aria-label={`Filtrar coluna ${label(c)}`}
                    value={colFilters[c] || ""}
                    onChange={(e) => {
                      setColFilters((prev) => ({ ...prev, [c]: e.target.value }));
                      setPage(0);
                    }}
                    style={{ width: "100%", marginTop: 4, fontSize: "0.75rem" }}
                  />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map(({ r, i }) => (
              <tr key={i}>
                {selectable ? (
                  <td>
                    <input
                      type="checkbox"
                      checked={selected.has(i)}
                      onChange={() => toggleRow(i)}
                      aria-label={`Selecionar linha ${i + 1}`}
                    />
                  </td>
                ) : null}
                {columns.map((c) => (
                  <td key={c}>
                    <Cell value={r[c]} column={c} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row" style={{ gap: 8 }}>
        <button type="button" className="btn" disabled={safePage <= 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>
          Anterior
        </button>
        <span className="muted" style={{ fontSize: "0.85rem" }}>
          Página {safePage + 1} de {pageCount}
        </span>
        <button
          type="button"
          className="btn"
          disabled={safePage >= pageCount - 1}
          onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
        >
          Próxima
        </button>
      </div>
    </div>
  );
}

function Cell({ value, column }: { value: unknown; column: string }) {
  if (value === null || value === undefined || value === "") {
    return <span className="muted">—</span>;
  }
  const s = String(value);
  if (/valor|value|amount|preco|price/i.test(column) && /^-?\d+(\.\d+)?$/.test(s)) {
    const n = Number(s);
    if (Number.isFinite(n)) {
      return (
        <span className="num">
          {n.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 })}
        </span>
      );
    }
  }
  if (s.length > 120) {
    return <span title={s}>{s.slice(0, 117)}…</span>;
  }
  return <>{s}</>;
}
