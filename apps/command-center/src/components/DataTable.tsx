/** Business-friendly table for CSV/JSONL/JSON list artifacts. */

export function DataTable({
  columns,
  rows,
  caption,
  maxHeight = 420,
}: {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  caption?: string;
  maxHeight?: number;
}) {
  if (!columns.length || !rows.length) {
    return <p className="muted">Nenhuma linha para exibir nesta amostra.</p>;
  }
  const label = (col: string) =>
    col
      .replace(/_/g, " ")
      .replace(/\bcnpj\b/gi, "CNPJ")
      .replace(/\buf\b/gi, "UF");

  return (
    <div className="table-wrap" style={{ maxHeight }}>
      <table className="data">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{label(c)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
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
  );
}

function Cell({ value, column }: { value: unknown; column: string }) {
  if (value === null || value === undefined || value === "") {
    return <span className="muted">—</span>;
  }
  const s = String(value);
  // Money-ish
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
