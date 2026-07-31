import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { client } from "../api/client";

const NAV = [
  { label: "Início", href: "/" },
  { label: "Oportunidades Extra", href: "/extra" },
  { label: "Fornecedores", href: "/confenge/suppliers" },
  { label: "Órgãos públicos", href: "/confenge/agencies" },
  { label: "Documentos", href: "/documents" },
  { label: "Revisões", href: "/review" },
  { label: "Resultados", href: "/results" },
  { label: "Atividades", href: "/jobs" },
  { label: "Todas as ações", href: "/actions" },
];

export function CommandPalette({
  open,
  onClose,
  onToggleTheme,
}: {
  open: boolean;
  onClose: () => void;
  onToggleTheme: () => void;
}) {
  const [q, setQ] = useState("");
  const [remote, setRemote] = useState<Array<{ label: string; href: string; detail?: string }>>([]);
  const [active, setActive] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    setQ("");
    setActive(0);
  }, [open]);

  useEffect(() => {
    if (!open || q.trim().length < 2) {
      setRemote([]);
      return;
    }
    const t = setTimeout(() => {
      void client.search(q).then((res) => {
        setRemote(
          res.results.map((r) => ({
            label: r.label,
            href: r.href.replace("/capabilities/", "/actions/").replace("/artifacts", "/results"),
            detail: r.detail,
          })),
        );
      });
    }, 180);
    return () => clearTimeout(t);
  }, [q, open]);

  const items = useMemo(() => {
    const local = [
      ...NAV.map((n) => ({ label: `Ir para ${n.label}`, href: n.href, detail: "Navegação" })),
      { label: "Alternar tema claro/escuro", href: "__theme__", detail: "Preferência" },
      {
        label: "Gerar lista de fornecedores",
        href: "/actions/confenge.suppliers.cycle.run",
        detail: "Ação CONFENGE",
      },
      {
        label: "Gerar lista de órgãos públicos",
        href: "/actions/confenge.public_agencies.cycle.run",
        detail: "Ação CONFENGE",
      },
      { label: "Rodar ciclo semanal Extra", href: "/actions/extra.weekly.run", detail: "Ação Extra" },
    ].filter((i) => !q || i.label.toLowerCase().includes(q.toLowerCase()));
    return [...local, ...remote].slice(0, 20);
  }, [q, remote]);

  useEffect(() => {
    setActive(0);
  }, [items.length, q]);

  if (!open) return null;

  const run = (href: string) => {
    if (href === "__theme__") {
      onToggleTheme();
      onClose();
      return;
    }
    navigate(href.startsWith("/") ? href : "/");
    onClose();
  };

  return (
    <div className="palette-backdrop" role="presentation" onClick={onClose}>
      <div className="palette" role="dialog" aria-label="Ações rápidas" onClick={(e) => e.stopPropagation()}>
        <input
          autoFocus
          placeholder="Buscar ou executar… (Ctrl+K)"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, items.length - 1));
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            }
            if (e.key === "Enter" && items[active]) run(items[active].href);
          }}
        />
        <ul>
          {items.map((item, idx) => (
            <li key={`${item.href}-${item.label}`}>
              <button
                type="button"
                data-active={idx === active}
                onMouseEnter={() => setActive(idx)}
                onClick={() => run(item.href)}
              >
                <div>{item.label}</div>
                {item.detail ? (
                  <div className="muted" style={{ fontSize: "0.8rem" }}>
                    {item.detail}
                  </div>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
