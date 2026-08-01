import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { client } from "../api/client";
import { APP_ROUTES } from "../App";

/** Canonical navigation actions — derived from declared app routes where possible. */
const ROUTE_LABELS: Record<string, string> = {
  "/": "Início",
  "/work/start": "Iniciar trabalho",
  "/extra": "Oportunidades Extra",
  "/confenge/suppliers": "Fornecedores",
  "/confenge/agencies": "Órgãos públicos",
  "/documents": "Documentos",
  "/review": "Revisões",
  "/results": "Entregáveis",
  "/jobs": "Atividades",
  "/actions": "Todas as ações",
  "/compare": "O que mudou",
  "/onboarding": "Configuração inicial",
  "/search": "Busca",
};

const WORKFLOW_ACTIONS = [
  {
    label: "Gerar lista de fornecedores",
    href: "/work/start/workflow.confenge.suppliers",
    detail: "Fluxo CONFENGE",
  },
  {
    label: "Gerar lista de órgãos públicos",
    href: "/work/start/workflow.confenge.agencies",
    detail: "Fluxo CONFENGE",
  },
  {
    label: "Rodar ciclo semanal Extra",
    href: "/work/start/workflow.extra.opportunities",
    detail: "Fluxo Extra",
  },
] as const;

type Item = { label: string; href: string; detail?: string };

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
  const [remote, setRemote] = useState<Item[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const listId = useId();
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    setQ("");
    setActive(0);
    setRemote([]);
    setError(null);
    const t = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => {
      window.clearTimeout(t);
      previouslyFocused.current?.focus?.();
    };
  }, [open]);

  useEffect(() => {
    if (!open || q.trim().length < 2) {
      setRemote([]);
      setError(null);
      return;
    }
    const controller = new AbortController();
    const t = window.setTimeout(() => {
      void client
        .search(q, controller.signal)
        .then((res) => {
          if (controller.signal.aborted) return;
          setError(null);
          setRemote(
            res.results.map((r) => ({
              label: r.label,
              href: r.href.replace("/capabilities/", "/actions/").replace("/artifacts", "/results"),
              detail: r.detail,
            })),
          );
        })
        .catch((err: Error) => {
          if (controller.signal.aborted) return;
          if (err.name === "AbortError") return;
          setError(err.message || "Falha na busca");
          setRemote([]);
        });
    }, 180);
    return () => {
      controller.abort();
      window.clearTimeout(t);
    };
  }, [q, open]);

  const items = useMemo(() => {
    const navItems: Item[] = APP_ROUTES.filter((r) => ROUTE_LABELS[r]).map((href) => ({
      label: `Ir para ${ROUTE_LABELS[href]}`,
      href,
      detail: "Navegação",
    }));
    const local: Item[] = [
      ...navItems,
      { label: "Alternar tema claro/escuro", href: "__theme__", detail: "Preferência" },
      ...WORKFLOW_ACTIONS,
    ].filter((i) => !q || i.label.toLowerCase().includes(q.toLowerCase()));
    return [...local, ...remote].slice(0, 20);
  }, [q, remote]);

  useEffect(() => {
    setActive(0);
  }, [q, items.length]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab" || !panelRef.current) return;
      const focusables = panelRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  if (!open) return null;

  const safeActive = items.length === 0 ? 0 : Math.min(Math.max(active, 0), items.length - 1);

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
        ref={panelRef}
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id={titleId} className="sr-only">
          Ações rápidas
        </h2>
        <label className="sr-only" htmlFor="cc-command-palette-input">
          Buscar ou executar ação
        </label>
        <input
          id="cc-command-palette-input"
          ref={inputRef}
          placeholder="Buscar ou executar… (Ctrl+K)"
          value={q}
          aria-label="Buscar ou executar ação"
          aria-controls={listId}
          aria-autocomplete="list"
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            if (e.key === "ArrowDown") {
              e.preventDefault();
              if (items.length === 0) return;
              setActive((a) => Math.min(Math.max(a, 0) + 1, items.length - 1));
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              if (items.length === 0) return;
              setActive((a) => Math.max(Math.min(a, items.length - 1) - 1, 0));
            }
            if (e.key === "Enter" && items[safeActive]) run(items[safeActive].href);
          }}
        />
        {error ? (
          <div className="muted" role="alert" style={{ padding: "8px 12px" }}>
            {error}
          </div>
        ) : null}
        <ul id={listId} role="listbox" aria-label="Resultados da busca">
          {items.length === 0 ? (
            <li className="muted" style={{ padding: "12px" }} role="presentation">
              Nenhum resultado
            </li>
          ) : (
            items.map((item, idx) => (
              <li key={`${item.href}-${item.label}`} role="presentation">
                <button
                  type="button"
                  role="option"
                  aria-selected={idx === safeActive}
                  data-active={idx === safeActive}
                  onMouseEnter={() => setActive(idx)}
                  onClick={() => run(item.href)}
                >
                  <span className="palette-item-label">{item.label}</span>
                  {item.detail ? (
                    <span className="muted palette-item-detail" style={{ display: "block", fontSize: "0.8rem" }}>
                      {item.detail}
                    </span>
                  ) : null}
                </button>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
