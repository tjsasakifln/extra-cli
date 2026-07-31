import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { client, type Capability } from "../api/client";
import { CapabilityCard } from "../components/CapabilityCard";
import { CoverageBar } from "../components/CoverageBar";
import { EmptyState } from "../components/EmptyState";
import { SkeletonState } from "../components/SkeletonState";

const AREA_META: Record<
  string,
  { title: string; description: string; category: string; notes: string[]; coverageExample?: { label: string; n: number; d: number }[] }
> = {
  extra: {
    title: "Operações da Extra",
    description:
      "Fluxo: Perfil → Coleta semanal → Classificação → Oportunidades acionáveis → Revisão humana → Decisão → Pacote → Acompanhamento.",
    category: "extra",
    notes: [
      "Nenhum outreach automático.",
      "Decisões humanas ficam registradas com confirmação quando sensíveis.",
    ],
  },
  suppliers: {
    title: "CONFENGE — Fornecedores",
    description:
      "Cadastro oficial, cobertura com denominador, ciclo comercial, revisão e outcome ledger. Sem percentuais órfãos.",
    category: "confenge_suppliers",
    notes: [
      "Nunca apresentar 100% sem informar o universo medido.",
      "Outreach automático permanece indisponível por segurança.",
    ],
    coverageExample: [
      { label: "Top 20 com cadastro oficial (exemplo de apresentação)", n: 20, d: 20 },
      { label: "População comercial com cadastro oficial (exemplo de apresentação)", n: 1071, d: 22882 },
    ],
  },
  agencies: {
    title: "CONFENGE — Órgãos Públicos",
    description:
      "Área separada de fornecedores. Linguagem cautelosa: potencial elegibilidade exige validação jurídica do órgão.",
    category: "confenge_agencies",
    notes: [
      "A interface nunca afirma “Pode contratar por dispensa”.",
      "Use: “Potencialmente elegível para análise de contratação direta.”",
    ],
  },
  documents: {
    title: "Documentos de Processos",
    description:
      "Discovery, cobertura, corpus e incremental. Categorias exibidas separadamente — sem média única que esconda gaps.",
    category: "process_documents",
    notes: [
      "Edital/anexos, sessão/julgamento, proposta vencedora e habilitação são eixos distintos.",
    ],
  },
  ops: {
    title: "Operação e Infraestrutura",
    description: "Somente leitura por padrão: saúde, freshness, timers, soak, jobs e falhas recentes.",
    category: "ops",
    notes: [
      "Sem reinício genérico de serviços na v1.",
      "Mutações exigiriam confirmação e allowlist específica.",
    ],
  },
  dod: {
    title: "DOD e Evidências",
    description:
      "Transparência de itens, evidências e campanhas. Aceite automático é proibido; apenas o controller canônico com gates.",
    category: "dod",
    notes: ["O Command Center não marca [x] no DOD.md."],
  },
};

export function AreaPage({ area }: { area: keyof typeof AREA_META }) {
  const meta = AREA_META[area];
  const q = useQuery({
    queryKey: ["capabilities", meta.category],
    queryFn: () => client.capabilities(meta.category),
  });

  return (
    <div>
      <header className="page-header">
        <h1>{meta.title}</h1>
        <p>{meta.description}</p>
      </header>

      <section className="panel">
        <h2>Princípios desta área</h2>
        <ul>
          {meta.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
        {meta.coverageExample ? (
          <div className="stack" style={{ marginTop: 12 }}>
            <h3>Cobertura com denominador</h3>
            {meta.coverageExample.map((c) => (
              <CoverageBar key={c.label} label={c.label} numerator={c.n} denominator={c.d} />
            ))}
            <p className="muted" style={{ margin: 0 }}>
              Exemplos ilustram o formato obrigatório. Números reais vêm dos artifacts/capabilities quando disponíveis.
            </p>
          </div>
        ) : null}
      </section>

      <section style={{ marginTop: 16 }}>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>Capabilities</h2>
          <Link className="btn" to="/capabilities">
            Ver todas
          </Link>
        </div>
        {q.isLoading ? <SkeletonState /> : null}
        {q.data?.capabilities?.length === 0 ? (
          <EmptyState title="Nenhuma capability nesta categoria" />
        ) : (
          <div className="grid-2">
            {(q.data?.capabilities || []).map((cap: Capability) => (
              <CapabilityCard key={cap.id} cap={cap} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
