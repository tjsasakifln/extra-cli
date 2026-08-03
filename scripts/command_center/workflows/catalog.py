"""Outcome-first guided workflows (not capability names)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WorkflowParam:
    name: str
    label: str
    type: str = "string"  # string|int|bool|select|date
    required: bool = False
    default: Any = None
    choices: list[str] | None = None
    description: str = ""
    advanced: bool = False


@dataclass(frozen=True)
class WorkflowDef:
    id: str
    title: str
    subtitle: str
    client_id: str
    client_label: str
    outcome: str
    description: str
    steps: list[str]
    expected_deliverables: list[str]
    params: list[WorkflowParam] = field(default_factory=list)
    supports_fixture: bool = True
    output_profiles: list[str] = field(default_factory=lambda: ["INTERNAL_ANALYSIS", "CLIENT_READY"])
    limitations: list[str] = field(default_factory=list)
    no_outreach: bool = True


WORKFLOWS: dict[str, WorkflowDef] = {
    "workflow.extra.opportunities": WorkflowDef(
        id="workflow.extra.opportunities",
        title="Encontrar oportunidades para a Extra",
        subtitle="Shortlist acionável a partir do perfil e do ciclo semanal",
        client_id="extra-construtora",
        client_label="Extra Construtora",
        outcome="Relatório executivo + workbook de oportunidades + pacote de revisão",
        description=(
            "Gera e organiza oportunidades aderentes ao perfil da Extra, com evidências, "
            "limites e decisões humanas por item — sem terminal e sem paths manuais."
        ),
        steps=[
            "Conferir perfil ativo",
            "Aplicar período e abrangência recomendados",
            "Processar shortlist",
            "Gerar PDF e XLSX",
            "Abrir revisão por oportunidade",
        ],
        expected_deliverables=[
            "Relatório executivo PDF",
            "Workbook XLSX",
            "Pacote de evidências",
            "run-manifest.json",
        ],
        params=[
            WorkflowParam(
                "period_days",
                "Período (dias)",
                type="int",
                default=7,
                description="Janela de oportunidades a considerar (padrão 7 dias).",
            ),
            WorkflowParam(
                "max_shortlist",
                "Tamanho da shortlist",
                type="int",
                default=15,
            ),
            WorkflowParam(
                "data_mode",
                "Modo de execução",
                type="select",
                default="FIXTURE",
                choices=["REAL", "FIXTURE"],
                description=(
                    "REAL = pipelines canônicos (exige preflight READY). "
                    "FIXTURE = demonstração explícita (não é evidência comercial)."
                ),
            ),
            WorkflowParam(
                "use_fixture",
                "Atalho: dados de demonstração",
                type="bool",
                default=True,
                advanced=True,
                description="Compatibilidade: true→FIXTURE, false→REAL. Prefira data_mode.",
            ),
            WorkflowParam(
                "output_profile",
                "Perfil de saída",
                type="select",
                default="CLIENT_READY",
                choices=["INTERNAL_ANALYSIS", "CLIENT_READY", "AUDIT_EVIDENCE"],
                advanced=True,
            ),
        ],
        limitations=[
            "A shortlist é preliminar até revisão humana.",
            "Modo REAL exige LOCAL_DATALAKE_DSN e preflight READY; bloqueios não caem em fixture.",
            "Modo FIXTURE é demonstração e não prova LIVE comercial.",
        ],
    ),
    "workflow.confenge.suppliers": WorkflowDef(
        id="workflow.confenge.suppliers",
        title="Encontrar empresas com potencial comercial",
        subtitle="Prospecção CONFENGE de fornecedores com cadastro oficial",
        client_id="confenge-suppliers",
        client_label="CONFENGE · Fornecedores",
        outcome="Lista comercial + dossiês + planilha de trabalho",
        description=(
            "Recorte geográfico e temporal de empresas com contratos públicos, "
            "respeitando cobertura do cadastro oficial e o router canônico."
        ),
        steps=[
            "Mostrar cobertura do cadastro oficial",
            "Aplicar recorte (UF/período/quantidade)",
            "Gerar ranking e dossiês",
            "Exportar PDF e XLSX comercial",
            "Selecionar prospects para revisão",
        ],
        expected_deliverables=[
            "Relatório executivo PDF",
            "Planilha XLSX comercial",
            "Evidências + manifest",
        ],
        params=[
            WorkflowParam("uf", "UF", default="SC", description="Estado de recorte (ex.: SC)."),
            WorkflowParam("max_companies", "Quantidade (Top N)", type="int", default=10),
            WorkflowParam(
                "population_mode",
                "Abrangência",
                type="select",
                default="BOUNDED_SAMPLE",
                choices=["BOUNDED_SAMPLE", "FULL_POPULATION"],
                description="BOUNDED_SAMPLE = amostra; FULL_POPULATION exige evidência de varredura integral.",
            ),
            WorkflowParam(
                "data_mode",
                "Modo de execução",
                type="select",
                default="FIXTURE",
                choices=["REAL", "FIXTURE"],
                description="REAL = confenge_commercial_target_router --target suppliers.",
            ),
            WorkflowParam(
                "use_fixture",
                "Atalho: dados de demonstração",
                type="bool",
                default=True,
                advanced=True,
                description="Compatibilidade: true→FIXTURE, false→REAL.",
            ),
            WorkflowParam(
                "output_profile",
                "Perfil de saída",
                type="select",
                default="CLIENT_READY",
                choices=["INTERNAL_ANALYSIS", "CLIENT_READY", "AUDIT_EVIDENCE"],
                advanced=True,
            ),
        ],
        limitations=[
            "Cobertura do Top N ≠ cobertura da população integral.",
            "Nenhum envio automático de e-mail ou WhatsApp.",
            "REAL bloqueado sem cadastro/DSN não cai em fixture.",
        ],
    ),
    "workflow.confenge.public_agencies": WorkflowDef(
        id="workflow.confenge.public_agencies",
        title="Encontrar órgãos que podem precisar de serviços técnicos",
        subtitle="Vertical CONFENGE para órgãos públicos (análise preliminar)",
        client_id="confenge-agencies",
        client_label="CONFENGE · Órgãos públicos",
        outcome="Lista de órgãos + classificações revisáveis + dossiês",
        description=(
            "Identifica oportunidades reativas e prospects institucionais proativos, "
            "com classificação jurídica preliminar e riscos explícitos."
        ),
        steps=[
            "Escolher UF e modalidade",
            "Gerar lista de órgãos",
            "Revisar classificação e conflitos",
            "Gerar PDF/XLSX e pacote de revisão",
        ],
        expected_deliverables=[
            "Relatório PDF",
            "Workbook XLSX",
            "Pacote de revisão",
            "Manifest + checksums",
        ],
        params=[
            WorkflowParam("uf", "UF", default="SC"),
            WorkflowParam("max_leads", "Quantidade máxima", type="int", default=10),
            WorkflowParam(
                "mode",
                "Modalidade",
                type="select",
                default="REACTIVE_OPPORTUNITY",
                choices=["REACTIVE_OPPORTUNITY", "PROACTIVE_INSTITUTIONAL_PROSPECT"],
            ),
            WorkflowParam(
                "data_mode",
                "Modo de execução",
                type="select",
                default="FIXTURE",
                choices=["REAL", "FIXTURE"],
                description="REAL = confenge_commercial_target_router --target public-agencies.",
            ),
            WorkflowParam(
                "use_fixture",
                "Atalho: dados de demonstração",
                type="bool",
                default=True,
                advanced=True,
                description="Compatibilidade: true→FIXTURE, false→REAL.",
            ),
            WorkflowParam(
                "output_profile",
                "Perfil de saída",
                type="select",
                default="CLIENT_READY",
                choices=["INTERNAL_ANALYSIS", "CLIENT_READY", "AUDIT_EVIDENCE"],
                advanced=True,
            ),
        ],
        limitations=[
            "Conclusões jurídicas são PRELIMINARES e revisáveis.",
            "Nunca afirma contratação direta garantida.",
            "Risco de fracionamento e conflitos devem ser validados por humano.",
            "REAL sem preflight READY não usa fixture silenciosamente.",
        ],
    ),
    "workflow.process_documents": WorkflowDef(
        id="workflow.process_documents",
        title="Analisar documentos de processos e editais",
        subtitle="Cobertura documental, PDFs no navegador e índice exportável",
        client_id="process-documents",
        client_label="Análises documentais",
        outcome="Índice XLSX + relatório de cobertura PDF + pacote selecionável",
        description=(
            "Pesquisa por entidade/processo/edital, organiza documentos por categoria "
            "e gera pacote de cobertura com proveniência."
        ),
        steps=[
            "Pesquisar identificador",
            "Listar documentos e cobertura",
            "Abrir PDFs no navegador",
            "Gerar índice e relatório",
        ],
        expected_deliverables=[
            "Relatório de cobertura PDF",
            "Índice XLSX",
            "Manifest com hashes",
        ],
        params=[
            WorkflowParam(
                "query",
                "Processo, edital, entidade ou objeto",
                default="demo-processo-001",
                required=True,
            ),
            WorkflowParam(
                "data_mode",
                "Modo de execução",
                type="select",
                default="FIXTURE",
                choices=["REAL", "FIXTURE"],
                description="REAL = python -m scripts.process_documents show <query>.",
            ),
            WorkflowParam(
                "use_fixture",
                "Atalho: acervo de demonstração",
                type="bool",
                default=True,
                advanced=True,
                description="Compatibilidade: true→FIXTURE, false→REAL.",
            ),
        ],
        limitations=[
            "Métricas de edital/anexos, sessão/julgamento, proposta e habilitação são separadas.",
            "Ausência de documento é reportada; não inventamos cobertura.",
            "REAL fail-closed quando o acervo/comando não puder executar.",
        ],
    ),
    "workflow.review.pending": WorkflowDef(
        id="workflow.review.pending",
        title="Revisar trabalho pendente",
        subtitle="Fila humana por cliente, campanha e tipo",
        client_id="workspace",
        client_label="Workspace",
        outcome="Decisões auditáveis com evidência e hashes",
        description="Abre a fila de revisão com contadores e decisões ACCEPT/REJECT/DEFER evidência-bound.",
        steps=["Abrir fila", "Revisar evidência", "Registrar decisão", "Regenerar se necessário"],
        expected_deliverables=["Histórico de decisões", "Itens atualizados"],
        params=[],
        supports_fixture=False,
        limitations=["Decisões não disparam outreach nem autoaceite de DOD."],
    ),
    "workflow.edital_case": WorkflowDef(
        id="workflow.edital_case",
        title="Análise técnica de edital",
        subtitle="Documento → exigências → análise → evidência",
        client_id="consulting-edital",
        client_label="Consultoria · Edital",
        outcome="Case pack de triagem técnica com findings e evidências",
        description=(
            "Ingere documentos do edital, extrai exigências e produz análise técnica "
            "citável — sem parecer jurídico automático."
        ),
        steps=[
            "Informar case_id e pasta de origem",
            "Ingerir documentos",
            "Analisar exigências",
            "Gerar relatórios",
            "Revisão humana",
        ],
        expected_deliverables=["Relatório de análise", "Findings JSON", "run-manifest.json"],
        params=[
            WorkflowParam("case_id", "ID do caso", default="cc-edital-case"),
            WorkflowParam(
                "source",
                "Arquivo/pasta de documentos (REAL) ou fixture",
                default="tests/edital_case/fixtures/sample_edital.pdf",
            ),
            WorkflowParam(
                "data_mode",
                "Modo de execução",
                type="select",
                default="FIXTURE",
                choices=["REAL", "FIXTURE"],
            ),
            WorkflowParam(
                "use_fixture",
                "Atalho: dados de demonstração",
                type="bool",
                default=True,
                advanced=True,
            ),
        ],
        limitations=[
            "Não é parecer jurídico.",
            "REAL exige fonte de documentos válida; sem fallback silencioso.",
            "FIXTURE é demonstração e deve aparecer como tal.",
        ],
    ),
    "workflow.budget_audit": WorkflowDef(
        id="workflow.budget_audit",
        title="Auditoria de orçamento e planilha",
        subtitle="Planilha → aritmética/BDI → divergências com referência",
        client_id="consulting-budget",
        client_label="Consultoria · Orçamento",
        outcome="Findings de orçamento com locators e trilha de evidência",
        description=(
            "Importa planilha de orçamento, valida totais/unidades/BDI e compara "
            "com referência oficial quando disponível."
        ),
        steps=[
            "Informar planilha",
            "Normalizar itens",
            "Auditar aritmética e BDI",
            "Comparar referências",
            "Gerar relatório",
        ],
        expected_deliverables=["Findings JSON", "Relatório PDF/XLSX", "run-manifest.json"],
        params=[
            WorkflowParam("case_id", "ID do caso", default="cc-budget-audit"),
            WorkflowParam(
                "source",
                "Arquivo de orçamento",
                default="tests/budget_audit/fixtures/operational_public_style_budget.xlsx",
            ),
            WorkflowParam(
                "data_mode",
                "Modo de execução",
                type="select",
                default="FIXTURE",
                choices=["REAL", "FIXTURE"],
            ),
            WorkflowParam(
                "use_fixture",
                "Atalho: dados de demonstração",
                type="bool",
                default=True,
                advanced=True,
            ),
        ],
        limitations=[
            "Comparação SINAPI/SICRO oficial exige dataset com proveniência.",
            "Findings não fecham GO comercial sozinhos.",
        ],
    ),
    "workflow.technical_acervo": WorkflowDef(
        id="workflow.technical_acervo",
        title="Consulta ao acervo técnico",
        subtitle="Exigência × acervo canônico da Extra",
        client_id="consulting-acervo",
        client_label="Consultoria · Acervo",
        outcome="Match de serviços/quantidades com scores e revisão humana",
        description=(
            "Consulta a fonte canônica data/extra_technical_acervo.json e retorna "
            "matches com confiança — sem habilitar submissão."
        ),
        steps=["Informar serviço/quantidade", "Consultar acervo", "Revisar matches"],
        expected_deliverables=["technical_acervo_result.json", "run-manifest.json"],
        params=[
            WorkflowParam("service", "Serviço / descrição", default="alvenaria", required=True),
            WorkflowParam("qty", "Quantidade", type="int", default=100),
            WorkflowParam("unit", "Unidade", default="m2"),
            WorkflowParam(
                "data_mode",
                "Modo de execução",
                type="select",
                default="FIXTURE",
                choices=["REAL", "FIXTURE"],
            ),
        ],
        limitations=[
            "Fonte canônica única: data/extra_technical_acervo.json.",
            "Match não autoriza submissão nem READY_TO_SUBMIT.",
        ],
    ),
    "workflow.bid_readiness": WorkflowDef(
        id="workflow.bid_readiness",
        title="Bid readiness / prontidão de proposta",
        subtitle="Exigências × documentos × acervo → revisão humana",
        client_id="consulting-bid",
        client_label="Consultoria · Bid readiness",
        outcome="Package de prontidão com blockers e revisão humana obrigatória",
        description=(
            "Monta matriz exigência×documento, cruza acervo e produz package "
            "READY_FOR_HUMAN_REVIEW ou BLOCKED_* — nunca READY_TO_SUBMIT automático."
        ),
        steps=[
            "Informar requirements e documentos",
            "Classificar e casar evidências",
            "Cruzar acervo técnico",
            "Montar package",
            "Revisão humana",
        ],
        expected_deliverables=["Package JSON", "Relatórios", "run-manifest.json"],
        params=[
            WorkflowParam("case_id", "ID do caso", default="cc-bid-readiness"),
            WorkflowParam(
                "requirements",
                "Arquivo de requisitos",
                default="scripts/bid_readiness/fixtures/golden/requirements.json",
            ),
            WorkflowParam(
                "documents",
                "Pasta de documentos",
                default="scripts/bid_readiness/fixtures/golden/documents",
            ),
            WorkflowParam(
                "data_mode",
                "Modo de execução",
                type="select",
                default="FIXTURE",
                choices=["REAL", "FIXTURE"],
            ),
            WorkflowParam(
                "use_fixture",
                "Atalho: dados de demonstração",
                type="bool",
                default=True,
                advanced=True,
            ),
        ],
        limitations=[
            "Nunca emite READY_TO_SUBMIT / HABILITADA automaticamente.",
            "Somente READY_FOR_HUMAN_REVIEW ou BLOCKED_*.",
        ],
    ),
}


def list_workflows() -> list[WorkflowDef]:
    return list(WORKFLOWS.values())


def get_workflow(workflow_id: str) -> WorkflowDef | None:
    return WORKFLOWS.get(workflow_id)
