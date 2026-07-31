import { useQuery } from "@tanstack/react-query";
import { client } from "../api/client";
import { SkeletonState } from "../components/SkeletonState";
import { StatusBadge } from "../components/StatusBadge";

export function OnboardingPage() {
  const q = useQuery({ queryKey: ["onboarding"], queryFn: client.onboarding });
  if (q.isLoading) return <SkeletonState />;
  const d = q.data || {};

  return (
    <div>
      <header className="page-header">
        <h1>Onboarding</h1>
        <p>
          Checklist local para abrir o Centro de Comando. Secrets aparecem apenas como configurada /
          ausente / inválida.
        </p>
      </header>
      <section className="panel">
        <h2>Obrigatório para abrir a interface</h2>
        <ul>
          <li>
            Python{" "}
            <StatusBadge attention="healthy" label={String((d.python as { version?: string })?.version || "ok")} />
          </li>
          <li>
            Node{" "}
            <StatusBadge
              attention={(d.node as { ok?: boolean })?.ok ? "healthy" : "attention"}
              label={(d.node as { ok?: boolean })?.ok ? "ok" : "ausente (só para build)"}
            />
          </li>
          <li>
            SPA build{" "}
            <StatusBadge attention={d.spa_built ? "healthy" : "attention"} label={d.spa_built ? "presente" : "rodar build"} />
          </li>
        </ul>
      </section>
      <section className="panel">
        <h2>Variáveis (sem conteúdo)</h2>
        <ul>
          {Object.entries((d.env as Record<string, string>) || {}).map(([k, v]) => (
            <li key={k}>
              <span className="mono">{k}</span>: {v}
            </li>
          ))}
        </ul>
      </section>
      <section className="panel">
        <h2>Capabilities</h2>
        <p>
          {String(d.capabilities_available)} disponíveis de {String(d.capabilities_total)} registradas.
        </p>
        <p className="muted">Ausentes degradam com “Ainda não disponível nesta versão”.</p>
      </section>
    </div>
  );
}
