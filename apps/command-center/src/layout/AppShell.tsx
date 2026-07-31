import { useEffect, useId, useRef, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { BrandLogo } from "../components/BrandLogo";
import { CommandPalette } from "../components/CommandPalette";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { StatusBadge } from "../components/StatusBadge";
import { formatRelativePt } from "../lib/format";

const NAV_MAIN = [
  { to: "/", label: "Início", end: true },
  { to: "/work/start", label: "Iniciar trabalho" },
  { to: "/review", label: "Revisões" },
  { to: "/results", label: "Entregáveis" },
  { to: "/compare", label: "O que mudou" },
  { to: "/extra", label: "Extra" },
  { to: "/confenge/suppliers", label: "Fornecedores" },
  { to: "/confenge/agencies", label: "Órgãos públicos" },
  { to: "/documents", label: "Documentos" },
] as const;

const NAV_SECONDARY = [
  { to: "/jobs", label: "Atividades em andamento" },
  { to: "/actions", label: "Avançado (capabilities)" },
  { to: "/onboarding", label: "Configuração inicial" },
] as const;

function getTheme(): "light" | "dark" | "system" {
  return (localStorage.getItem("cc-theme") as "light" | "dark" | "system") || "system";
}

function applyTheme(mode: "light" | "dark" | "system") {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const resolved = mode === "system" ? (prefersDark ? "dark" : "light") : mode;
  document.documentElement.setAttribute("data-theme", resolved);
}

function healthUi(health: {
  isLoading: boolean;
  isError: boolean;
  isFetching: boolean;
  data?: Record<string, unknown>;
}): { attention: "running" | "healthy" | "attention" | "blocked_technical"; label: string } {
  if (health.isLoading || (health.isFetching && !health.data && !health.isError)) {
    return { attention: "running", label: "Verificando..." };
  }
  if (health.isError || !health.data) {
    return { attention: "blocked_technical", label: "Offline" };
  }
  const ok = health.data.ok === true || health.data.status === "ok" || health.data.status === "healthy";
  const degraded =
    health.data.degraded === true ||
    health.data.status === "degraded" ||
    (typeof health.data.services === "object" &&
      health.data.services !== null &&
      Object.values(health.data.services as Record<string, unknown>).some((v) => v === false || v === "down"));
  if (degraded || !ok) {
    return { attention: "attention", label: "Degradado" };
  }
  return { attention: "healthy", label: "Local OK" };
}

export function AppShell() {
  const [navOpen, setNavOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark" | "system">(getTheme);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();
  const menuBtnRef = useRef<HTMLButtonElement>(null);
  const scrimId = useId();

  const health = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => client.health(signal),
    refetchInterval: 15000,
  });
  const reviews = useQuery({
    queryKey: ["reviews", "pending", "nav"],
    queryFn: () => client.reviews("pending", 1, 0),
    refetchInterval: 12000,
  });
  const pendingCount = reviews.data?.total_count ?? reviews.data?.count ?? 0;
  const h = healthUi(health);
  const healthUpdated = health.dataUpdatedAt
    ? formatRelativePt(new Date(health.dataUpdatedAt).toISOString())
    : null;

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem("cc-theme", theme);
  }, [theme]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
      if (e.key === "Escape") {
        if (paletteOpen) setPaletteOpen(false);
        else if (navOpen) {
          setNavOpen(false);
          menuBtnRef.current?.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navOpen, paletteOpen]);

  useEffect(() => {
    if (!navOpen) {
      document.body.style.overflow = "";
      return;
    }
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [navOpen]);

  const cycleTheme = () => {
    setTheme((t) => (t === "system" ? "light" : t === "light" ? "dark" : "system"));
  };

  const closeNav = () => {
    setNavOpen(false);
    menuBtnRef.current?.focus();
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#conteudo-principal">
        Ir para o conteúdo
      </a>
      {navOpen ? (
        <button
          type="button"
          className="nav-scrim"
          id={scrimId}
          aria-label="Fechar menu"
          onClick={closeNav}
        />
      ) : null}
      <aside className={`sidebar ${navOpen ? "open" : ""}`} aria-label="Navegação principal" id="cc-sidebar">
        <div className="brand">
          <BrandLogo plate height={40} />
          <div>
            <strong className="brand-title">Centro de Comando</strong>
            <span className="brand-subtitle">
              Operação comercial e de oportunidades — feito para o consultor, não para o terminal
            </span>
          </div>
        </div>
        <nav>
          <div className="nav-section-label">Trabalho do dia</div>
          <ul className="nav-list">
            {NAV_MAIN.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={"end" in item ? item.end : false} onClick={closeNav}>
                  {item.label}
                  {item.to === "/review" && pendingCount > 0 ? (
                    <span
                      className="status-badge status-awaiting_human"
                      style={{ marginLeft: "auto" }}
                      aria-label={`${pendingCount} revisões pendentes`}
                    >
                      {pendingCount}
                    </span>
                  ) : null}
                </NavLink>
              </li>
            ))}
          </ul>
          <div className="nav-section-label">Mais</div>
          <ul className="nav-list">
            {NAV_SECONDARY.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} onClick={closeNav}>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="sidebar-foot">
          <div>Sistema local · só neste computador</div>
          <div style={{ marginTop: 4 }}>
            {h.label === "Offline" ? "Conexão com o painel indisponível" : "Painel local"}
          </div>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <button
            ref={menuBtnRef}
            type="button"
            className="btn mobile-nav-toggle"
            aria-label={navOpen ? "Fechar menu" : "Abrir menu"}
            aria-expanded={navOpen}
            aria-controls="cc-sidebar"
            onClick={() => setNavOpen((v) => !v)}
          >
            Menu
          </button>
          <form
            className="topbar-search"
            onSubmit={(e) => {
              e.preventDefault();
              if (search.trim()) navigate(`/search?q=${encodeURIComponent(search.trim())}`);
            }}
          >
            <label className="sr-only" htmlFor="global-search">
              Busca global
            </label>
            <input
              id="global-search"
              type="search"
              placeholder="Buscar empresa, órgão, CNPJ, resultado…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </form>
          <div className="topbar-health" title={healthUpdated ? `Atualizado ${healthUpdated}` : undefined}>
            <StatusBadge attention={h.attention} label={h.label} />
            {healthUpdated && h.label === "Local OK" ? (
              <span className="muted topbar-health-meta">{healthUpdated}</span>
            ) : null}
          </div>
          <button type="button" className="btn topbar-actions-secondary" onClick={() => setPaletteOpen(true)}>
            Ações rápidas <span className="kbd">Ctrl K</span>
          </button>
          <button type="button" className="btn topbar-actions-secondary" onClick={cycleTheme} aria-label="Alternar tema">
            Tema
          </button>
          <Link className="btn topbar-actions-secondary" to="/onboarding">
            Ajuda
          </Link>
        </header>
        <main id="conteudo-principal" className="content">
          <ErrorBoundary area="page">
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onToggleTheme={cycleTheme} />
    </div>
  );
}
