import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { client } from "../api/client";

const NAV = [
  { label: "Visão Geral", href: "/" },
  { label: "Operações da Extra", href: "/extra" },
  { label: "CONFENGE Fornecedores", href: "/confenge/suppliers" },
  { label: "CONFENGE Órgãos Públicos", href: "/confenge/agencies" },
  { label: "Documentos de Processos", href: "/documents" },
  { label: "Operação e Infraestrutura", href: "/ops" },
  { label: "DOD e Evidências", href: "/dod" },
  { label: "Jobs", href: "/jobs" },
  { label: "Revisão humana", href: "/review" },
  { label: "Capabilities", href: "/capabilities" },
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
        setRemote(res.results.map((r) => ({ label: r.label, href: r.href, detail: r.detail })));
      });
    }, 180);
    return () => clearTimeout(t);
  }, [q, open]);

  const items = useMemo(() => {
    const local = [
      ...NAV.map((n) => ({ label: `Ir para ${n.label}`, href: n.href, detail: "Navegação" })),
      { label: "Alternar tema", href: "__theme__", detail: "Preferência" },
      { label: "Rodar fixture seguro", href: "/capabilities/cc.fixture.echo", detail: "Ação" },
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
      <div
        className="palette"
        role="dialog"
        aria-label="Command palette"
        onClick={(e) => e.stopPropagation()}
      >
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
                {item.detail ? <div className="muted" style={{ fontSize: "0.8rem" }}>{item.detail}</div> : null}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
