import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { CommandPalette } from "../components/CommandPalette";
import { StatusBadge } from "../components/StatusBadge";

const NAV = [
  { to: "/", label: "Visão Geral", end: true },
  { to: "/extra", label: "Operações da Extra" },
  { to: "/confenge/suppliers", label: "CONFENGE Fornecedores" },
  { to: "/confenge/agencies", label: "CONFENGE Órgãos" },
  { to: "/documents", label: "Documentos" },
  { to: "/ops", label: "Operação / Infra" },
  { to: "/dod", label: "DOD e Evidências" },
  { to: "/jobs", label: "Jobs" },
  { to: "/review", label: "Revisão humana" },
  { to: "/capabilities", label: "Capabilities" },
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
          <strong>EXTRA Command Center</strong>
          <span>Camada visual local · extra-cli</span>
        </div>
        <nav>
          <ul className="nav-list">
            {NAV.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  onClick={() => setNavOpen(false)}
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div style={{ marginTop: 24 }} className="muted" >
          <div style={{ fontSize: "0.78rem" }}>
            SHA {String(health.data?.sha || "…")}
          </div>
          <div style={{ fontSize: "0.78rem", marginTop: 4 }}>
            Tema: {theme}
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
              placeholder="Buscar órgão, CNPJ, job, capability…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </form>
          <StatusBadge
            attention={health.isError ? "blocked_technical" : "healthy"}
            label={health.isError ? "API offline" : "API local"}
          />
          <button type="button" className="btn" onClick={() => setPaletteOpen(true)}>
            Comandos <span className="kbd">Ctrl K</span>
          </button>
          <button type="button" className="btn" onClick={cycleTheme} aria-label="Alternar tema">
            Tema
          </button>
          <Link className="btn" to="/onboarding">
            Setup
          </Link>
        </header>
        <main id="conteudo-principal" className="content">
          <Outlet />
        </main>
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onToggleTheme={cycleTheme} />
      <style>{`
        .sr-only {
          position: absolute;
          width: 1px;
          height: 1px;
          padding: 0;
          margin: -1px;
          overflow: hidden;
          clip: rect(0,0,0,0);
          border: 0;
        }
      `}</style>
    </div>
  );
}
