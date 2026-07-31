import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { BrandLogo } from "../components/BrandLogo";
import { CommandPalette } from "../components/CommandPalette";
import { StatusBadge } from "../components/StatusBadge";

const NAV_MAIN = [
  { to: "/", label: "Início", end: true },
  { to: "/work/start", label: "Iniciar trabalho" },
  { to: "/review", label: "Revisões" },
  { to: "/results", label: "Entregáveis" },
  { to: "/extra", label: "Extra" },
  { to: "/confenge/suppliers", label: "Fornecedores" },
  { to: "/confenge/agencies", label: "Órgãos públicos" },
  { to: "/documents", label: "Documentos" },
];

const NAV_SECONDARY = [
  { to: "/jobs", label: "Atividades em andamento" },
  { to: "/actions", label: "Avançado (capabilities)" },
  { to: "/onboarding", label: "Configuração inicial" },
];

function getTheme(): "light" | "dark" | "system" {
  return (localStorage.getItem("cc-theme") as "light" | "dark" | "system") || "system";
}

function applyTheme(mode: "light" | "dark" | "system") {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const resolved = mode === "system" ? (prefersDark ? "dark" : "light") : mode;
  document.documentElement.setAttribute("data-theme", resolved);
}

export function AppShell() {
  const [navOpen, setNavOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark" | "system">(getTheme);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();
  const health = useQuery({ queryKey: ["health"], queryFn: client.health, refetchInterval: 15000 });
  const reviews = useQuery({
    queryKey: ["reviews", "pending", "nav"],
    queryFn: () => client.reviews("pending"),
    refetchInterval: 12000,
  });
  const pendingCount = reviews.data?.count ?? reviews.data?.reviews?.length ?? 0;

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
      if (e.key === "Escape") setPaletteOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const cycleTheme = () => {
    setTheme((t) => (t === "system" ? "light" : t === "light" ? "dark" : "system"));
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#conteudo-principal">
        Ir para o conteúdo
      </a>
      <aside className={`sidebar ${navOpen ? "open" : ""}`} aria-label="Navegação principal">
        <div className="brand">
          <BrandLogo variant="auto" height={32} />
          <div>
            <strong>Centro de Comando</strong>
            <span>Operação comercial e de oportunidades — feito para o consultor, não para o terminal</span>
          </div>
        </div>
        <nav>
          <div className="nav-section-label">Trabalho do dia</div>
          <ul className="nav-list">
            {NAV_MAIN.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={item.end} onClick={() => setNavOpen(false)}>
                  {item.label}
                  {item.to === "/review" && pendingCount > 0 ? (
                    <span className="status-badge status-awaiting_human" style={{ marginLeft: "auto" }}>
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
                <NavLink to={item.to} onClick={() => setNavOpen(false)}>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="sidebar-foot">
          <div>Sistema local · só neste computador</div>
          <div style={{ marginTop: 4 }}>
            {health.isError ? "Conexão com o painel indisponível" : "Painel online"}
          </div>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <button
            type="button"
            className="btn mobile-nav-toggle"
            aria-label="Abrir menu"
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
          <StatusBadge
            attention={health.isError ? "blocked_technical" : "healthy"}
            label={health.isError ? "Offline" : "Local OK"}
          />
          <button type="button" className="btn" onClick={() => setPaletteOpen(true)}>
            Ações rápidas <span className="kbd">Ctrl K</span>
          </button>
          <button type="button" className="btn" onClick={cycleTheme} aria-label="Alternar tema">
            Tema
          </button>
          <Link className="btn" to="/onboarding">
            Ajuda
          </Link>
        </header>
        <main id="conteudo-principal" className="content">
          <Outlet />
        </main>
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onToggleTheme={cycleTheme} />
    </div>
  );
}
