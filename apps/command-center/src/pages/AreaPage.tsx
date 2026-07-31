import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { client, type Capability } from "../api/client";
import { BrandLogo } from "../components/BrandLogo";
import { CapabilityCard } from "../components/CapabilityCard";
import { CoverageBar } from "../components/CoverageBar";
import { EmptyState } from "../components/EmptyState";
import { SkeletonState } from "../components/SkeletonState";

const AREA_META: Record<
  string,
  {
    title: string;
    description: string;
    category: string;
    notes: string[];
    showBrand?: boolean;
    coverageExample?: { label: string; n: number; d: number }[];
  }
> = {
  extra: {
    title: "Oportunidades Extra",
    description:
      "Fluxo da consultoria: perfil → ciclo semanal → oportunidades acionáveis → sua revisão → pacote de acompanhamento.",
    category: "extra",
    notes: [
      "Nenhuma mensagem é enviada automaticamente a clientes ou órgãos.",
      "Decisões sensíveis pedem confirmação por escrito na tela.",
    ],
  },
  suppliers: {
    title: "Fornecedores CONFENGE",
    description:
      "Cadastro oficial, cobertura com total explícito, geração da lista comercial e resultados em tabela.",
    category: "confenge_suppliers",
    showBrand: true,
    notes: [
      "Nunca mostre “100%” sem dizer o universo medido.",
      "Envio automático de e-mail/WhatsApp permanece desligado por segurança.",
    ],
    coverageExample: [
      { label: "Top 20 com cadastro oficial (formato de apresentação)", n: 20, d: 20 },
      { label: "População comercial com cadastro oficial (formato de apresentação)", n: 1071, d: 22882 },
    ],
  },
  agencies: {
    title: "Órgãos públicos",
    description:
      "Área separada de fornecedores. Linguagem cautelosa: elegibilidade potencial exige validação jurídica do órgão.",
    category: "confenge_agencies",
    showBrand: true,
    notes: [
      "A interface nunca afirma “Pode contratar por dispensa”.",
      "Use: “Potencialmente elegível para análise de contratação direta.”",
    ],
  },
  documents: {
    title: "Documentos de processos",
    description:
      "Descoberta, coleta, cobertura e corpus. Cada categoria de documento aparece separada — sem média que esconda buracos.",
    category: "process_documents",
    notes: [
      "Edital/anexos, sessão/julgamento, proposta vencedora e habilitação são eixos distintos.",
    ],
  },
  ops: {
    title: "Saúde do sistema",
    description: "Consultas de saúde, fontes de dados e atividades recentes — em geral somente leitura.",
    category: "ops",
    notes: ["Sem reinício genérico de serviços na versão atual."],
  },
  dod: {
    title: "Evidências e checklist",
    description:
      "Transparência de itens e evidências. Aceite automático é proibido; só o processo canônico com gates.",
    category: "dod",
    notes: ["Este painel não marca itens do DOD sozinho."],
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
        {meta.showBrand ? (
          <div style={{ marginBottom: 12 }}>
            <BrandLogo variant="auto" height={34} />
          </div>
        ) : null}
        <h1>{meta.title}</h1>
        <p>{meta.description}</p>
      </header>

      <section className="panel">
        <h2>Antes de começar</h2>
        <ul>
          {meta.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
        {meta.coverageExample ? (
          <div className="stack" style={{ marginTop: 12 }}>
            <h3>Como mostramos cobertura (sempre com total)</h3>
            {meta.coverageExample.map((c) => (
              <CoverageBar key={c.label} label={c.label} numerator={c.n} denominator={c.d} />
            ))}
            <p className="muted" style={{ margin: 0 }}>
              Exemplos ilustram o formato. Os números reais vêm dos resultados gerados nas ações abaixo.
            </p>
          </div>
        ) : null}
      </section>

      <section style={{ marginTop: 16 }}>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>Ações desta área</h2>
          <Link className="btn" to="/actions">
            Ver todas
          </Link>
        </div>
        {q.isLoading ? <SkeletonState /> : null}
        {q.data?.capabilities?.length === 0 ? (
          <EmptyState title="Nenhuma ação nesta área" />
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
