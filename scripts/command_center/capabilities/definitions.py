"""Initial capability declarations for EXTRA Command Center."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from scripts.command_center.capabilities.base import (
    Capability,
    ParamSpec,
    RiskLevel,
    default_parse,
    python_m,
)
from scripts.command_center.config import REPO_ROOT


def _fixture_echo(params: dict[str, Any]) -> list[str]:
    import sys

    message = str(params.get("message") or "Command Center fixture OK")
    # Safe built-in: python -c without shell
    code = (
        "import sys,time;"
        f"print({message!r});"
        "print('PROGRESS 1/2', flush=True);"
        "time.sleep(0.2);"
        "print('PROGRESS 2/2', flush=True);"
        "print('FIXTURE_DONE', flush=True);"
        "sys.exit(0)"
    )
    return [sys.executable, "-c", code]


def _fixture_slow(params: dict[str, Any]) -> list[str]:
    import sys

    try:
        seconds = int(params.get("seconds") if params.get("seconds") is not None else 8)
    except (TypeError, ValueError):
        seconds = 8
    seconds = max(1, min(seconds, 60))
    code = (
        "import sys,time;"
        f"secs={seconds};"
        "print('SLOW_START', secs, flush=True);"
        "for i in range(secs):"
        " time.sleep(1);"
        " print(f'SLOW_TICK {i+1}/{secs}', flush=True);"
        "print('SLOW_DONE', flush=True);"
        "sys.exit(0)"
    )
    return [sys.executable, "-c", code]


def all_capabilities() -> list[Capability]:
    caps: list[Capability] = [
        Capability(
            id="cc.fixture.echo",
            name="Fixture de execução segura",
            description="Job de teste local sem rede, sem banco e sem side-effects operacionais.",
            category="ops",
            argv_builder=_fixture_echo,
            params=[
                ParamSpec(
                    name="message",
                    label="Mensagem",
                    default="Command Center fixture OK",
                    description="Texto ecoado nos logs do job.",
                )
            ],
            risk=RiskLevel.READ,
            fixture=True,
            parse_result=default_parse,
            output_roots=["data/command_center"],
        ),
        Capability(
            id="cc.fixture.slow",
            name="Fixture lenta (cancelável)",
            description="Job longo local para testar cancelamento — dorme alguns segundos.",
            category="ops",
            argv_builder=_fixture_slow,
            params=[
                ParamSpec(
                    name="seconds",
                    label="Duração (s)",
                    type="int",
                    default=8,
                    description="Tempo de espera antes de concluir (padrão 8s).",
                )
            ],
            risk=RiskLevel.READ,
            fixture=True,
            allow_cancel=True,
            parse_result=default_parse,
            timeout_sec=120,
            output_roots=["data/command_center"],
        ),
        # ── Extra ──────────────────────────────────────────────
        Capability(
            id="extra.profile.show",
            name="Mostrar perfil Extra",
            description="Exibe resumo e proveniência do perfil operacional da Extra.",
            category="extra",
            argv_builder=lambda p: python_m("scripts.ops.extra_profile", "show"),
            required_modules=["scripts.ops.extra_profile"],
            risk=RiskLevel.READ,
            parse_result=default_parse,
            docs=["docs/command-center/CAPABILITY-REGISTRY.md"],
        ),
        Capability(
            id="extra.profile.validate",
            name="Validar perfil Extra",
            description="Valida honestidade e estrutura do perfil; não altera produção.",
            category="extra",
            argv_builder=lambda p: python_m("scripts.ops.extra_profile", "validate"),
            required_modules=["scripts.ops.extra_profile"],
            risk=RiskLevel.READ,
            parse_result=default_parse,
        ),
        Capability(
            id="extra.weekly.run",
            name="Ciclo semanal Extra",
            description="Executa o ciclo operacional semanal canônico (collect→process→delivery).",
            category="extra",
            argv_builder=lambda p: _weekly_argv(p),
            params=[
                ParamSpec("strict", "Modo estrito", type="bool", default=True),
                ParamSpec("skip_collect", "Pular coleta (reusar lake)", type="bool", default=False),
                ParamSpec("offline", "Modo offline (teste)", type="bool", default=False, advanced=True),
                ParamSpec("limit", "Limite por lista", type="int", default=None, advanced=True),
                ParamSpec(
                    "output_dir",
                    "Diretório de saída",
                    type="path",
                    default=None,
                    advanced=True,
                    description="Opcional; default output/weekly/<cycle_id>",
                ),
            ],
            required_modules=["scripts.ops.weekly_cycle"],
            required_env=["LOCAL_DATALAKE_DSN"],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase="Confirmo a execução do ciclo semanal local.",
            output_roots=["output/weekly", "output"],
            parse_result=default_parse,
            timeout_sec=7200,
        ),
        Capability(
            id="extra.actionable.run",
            name="Oportunidades acionáveis",
            description="Gera shortlist acionável a partir do perfil e do weekly pack.",
            category="extra",
            argv_builder=lambda p: _actionable_argv(p),
            params=[
                ParamSpec("weekly_input", "Pacote weekly", type="path", required=True, example="output/weekly/..."),
                ParamSpec("out", "Diretório de saída", type="path", required=True),
            ],
            required_modules=["scripts.ops.extra_actionable"],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase="CONFIRMO",
            output_roots=["output"],
            parse_result=default_parse,
            expected_pr="main/extra_actionable",
        ),
        Capability(
            id="extra.decision.review",
            name="Revisar decisões (Extra)",
            description="Abre/lista pacote de revisão humana do decision loop.",
            category="extra",
            argv_builder=lambda p: python_m(
                "scripts.ops.extra_decision_review",
                *([p["path"]] if p.get("path") else []),
            ),
            params=[ParamSpec("path", "Caminho do pacote de decisão", type="path", required=False)],
            required_modules=["scripts.ops.extra_decision_review"],
            risk=RiskLevel.READ,
            parse_result=default_parse,
        ),
        Capability(
            id="extra.decision.finalize",
            name="Decision loop Extra",
            description="Roda o loop perfil→ação→decisão a partir de um weekly pack.",
            category="extra",
            argv_builder=lambda p: python_m(
                "scripts.ops.extra_decision_loop",
                "run",
                "--weekly-dir",
                str(p["weekly_input"]),
                "--out",
                str(p["out"]),
                *(["--max-shortlist", str(p["max_shortlist"])] if p.get("max_shortlist") else []),
            ),
            params=[
                ParamSpec("weekly_input", "Pacote weekly", type="path", required=True),
                ParamSpec("out", "Saída da decisão", type="path", required=True),
                ParamSpec("max_shortlist", "Tamanho da shortlist", type="int", default=None, advanced=True),
            ],
            required_modules=["scripts.ops.extra_decision_loop"],
            risk=RiskLevel.HUMAN_DECISION,
            requires_confirmation=True,
            confirmation_phrase=(
                "Confirmo que revisei os dados e autorizo apenas a geração local do pacote de decisão (sem outreach)."
            ),
            output_roots=["output"],
            parse_result=default_parse,
        ),
        Capability(
            id="extra.recurring.run",
            name="Recurring delivery Extra",
            description="Pacote recorrente: deltas, relatórios e alertas urgentes (local).",
            category="extra",
            argv_builder=lambda p: python_m(
                "scripts.ops.extra_recurring_delivery",
                "run",
                "--current-run",
                str(p["current_run"]),
                "--delivery-out",
                str(p["delivery_out"]),
                *(["--previous-run", str(p["previous_run"])] if p.get("previous_run") else []),
            ),
            params=[
                ParamSpec("current_run", "Run weekly atual", type="path", required=True),
                ParamSpec("delivery_out", "Saída externa/local", type="path", required=True),
                ParamSpec("previous_run", "Run anterior (opcional)", type="path", advanced=True),
            ],
            required_modules=["scripts.ops.extra_recurring_delivery"],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase="CONFIRMO",
            parse_result=default_parse,
        ),
        # ── CONFENGE suppliers ─────────────────────────────────
        # Router canônico: confenge_commercial_target_router
        # (suppliers | public-agencies | all) com precheck do cadastro oficial.
        Capability(
            id="confenge.suppliers.registry.health",
            name="Verificar cadastro oficial de empresas",
            description="Confere se o cadastro oficial de CNPJs está disponível e saudável.",
            category="confenge_suppliers",
            argv_builder=lambda p: _registry_argv("health", p),
            required_modules=["scripts.company_registry"],
            risk=RiskLevel.READ,
            parse_result=default_parse,
            expected_pr="company_registry",
        ),
        Capability(
            id="confenge.suppliers.registry.lookup",
            name="Consultar empresa por CNPJ",
            description="Busca uma empresa no cadastro oficial (somente consulta).",
            category="confenge_suppliers",
            argv_builder=lambda p: _registry_argv("lookup", p),
            params=[ParamSpec("cnpj", "CNPJ da empresa", required=True, example="00.000.000/0001-91")],
            required_modules=["scripts.company_registry"],
            risk=RiskLevel.READ,
            parse_result=default_parse,
        ),
        Capability(
            id="confenge.suppliers.registry.coverage",
            name="Cobertura do cadastro oficial",
            description="Mostra quantas empresas do universo comercial estão no cadastro (sempre com total).",
            category="confenge_suppliers",
            argv_builder=lambda p: _registry_argv("coverage", p),
            required_modules=["scripts.company_registry"],
            risk=RiskLevel.READ,
            parse_result=default_parse,
        ),
        Capability(
            id="confenge.suppliers.cycle.run",
            name="Gerar lista comercial de fornecedores",
            description=(
                "Roda o ciclo comercial canônico de fornecedores via router oficial "
                "(com checagem do cadastro). Não envia e-mail nem mensagem automática."
            ),
            category="confenge_suppliers",
            argv_builder=lambda p: _commercial_router_argv("suppliers", p),
            params=[
                ParamSpec(
                    "run_mode",
                    "Modo de execução",
                    type="select",
                    default="DRY_RUN",
                    choices=["DRY_RUN", "RC", "TEST", "EXPERIMENTAL_SAMPLE"],
                    description="DRY_RUN = simulação segura; RC = corrida real local.",
                ),
                ParamSpec("out", "Pasta de resultados", type="path", advanced=True),
                ParamSpec("max_contracts", "Limite de contratos", type="int", advanced=True),
                ParamSpec(
                    "population_mode",
                    "Abrangência",
                    type="select",
                    choices=["BOUNDED_SAMPLE", "FULL_POPULATION"],
                    default="BOUNDED_SAMPLE",
                    advanced=True,
                ),
            ],
            required_modules=["scripts.ops.confenge_commercial_target_router"],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase="Confirmo a geração local da lista comercial de fornecedores (sem envio automático).",
            parse_result=default_parse,
            timeout_sec=7200,
            output_roots=["output/confenge-commercial", "artifacts", "output"],
        ),
        # ── CONFENGE public agencies ───────────────────────────
        Capability(
            id="confenge.public_agencies.cycle.run",
            name="Gerar lista de órgãos públicos",
            description=(
                "Roda o ciclo canônico de órgãos públicos (router oficial). "
                "Resultados exigem validação jurídica — a tela nunca afirma contratação garantida."
            ),
            category="confenge_agencies",
            argv_builder=lambda p: _commercial_router_argv("public-agencies", p),
            params=[
                ParamSpec("uf", "UF (opcional)", default=None, example="SC", description="Filtrar por estado."),
                ParamSpec(
                    "max_public_agency_leads",
                    "Quantidade máxima de órgãos",
                    type="int",
                    default=20,
                ),
                ParamSpec(
                    "public_agency_mode",
                    "Tipo de prospecção",
                    type="select",
                    default=None,
                    choices=["REACTIVE_OPPORTUNITY", "PROACTIVE_INSTITUTIONAL_PROSPECT"],
                    advanced=True,
                ),
                ParamSpec("public_agency_out", "Pasta de resultados", type="path", advanced=True),
                ParamSpec(
                    "run_mode",
                    "Modo de execução",
                    type="select",
                    default="DRY_RUN",
                    choices=["DRY_RUN", "RC", "TEST", "EXPERIMENTAL_SAMPLE"],
                    advanced=True,
                ),
            ],
            required_modules=["scripts.ops.confenge_commercial_target_router"],
            required_env=["LOCAL_DATALAKE_DSN"],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase="Confirmo a geração local da lista de órgãos públicos (sem envio automático).",
            parse_result=default_parse,
            timeout_sec=7200,
            output_roots=["output/confenge-commercial", "artifacts", "output"],
        ),
        Capability(
            id="confenge.public_agencies.review.open",
            name="Abrir pacotes de revisão de órgãos",
            description="Lista pacotes que ainda precisam de sua decisão humana sobre órgãos públicos.",
            category="confenge_agencies",
            argv_builder=lambda p: python_m(
                "scripts.ops.confenge_human_review_packages",
                *(["--path", str(p["path"])] if p.get("path") else []),
            ),
            params=[ParamSpec("path", "Pasta do pacote", type="path", advanced=True)],
            required_modules=["scripts.ops.confenge_human_review_packages"],
            risk=RiskLevel.READ,
            parse_result=default_parse,
        ),
        Capability(
            id="confenge.all.cycle.run",
            name="Gerar fornecedores e órgãos juntos",
            description=(
                "Ciclo combinado canônico (target=all): fornecedores + órgãos em uma execução. "
                "Cada modalidade é avaliada à parte; um sucesso não aprova a outra."
            ),
            category="confenge_suppliers",
            argv_builder=lambda p: _commercial_router_argv("all", p),
            params=[
                ParamSpec(
                    "run_mode",
                    "Modo de execução",
                    type="select",
                    default="DRY_RUN",
                    choices=["DRY_RUN", "RC", "TEST", "EXPERIMENTAL_SAMPLE"],
                ),
                ParamSpec("out", "Pasta de resultados (fornecedores)", type="path", advanced=True),
                ParamSpec("public_agency_out", "Pasta de resultados (órgãos)", type="path", advanced=True),
                ParamSpec("max_contracts", "Limite de contratos", type="int", advanced=True),
                ParamSpec(
                    "max_public_agency_leads",
                    "Quantidade máxima de órgãos",
                    type="int",
                    default=20,
                    advanced=True,
                ),
                ParamSpec(
                    "population_mode",
                    "Abrangência (fornecedores)",
                    type="select",
                    choices=["BOUNDED_SAMPLE", "FULL_POPULATION"],
                    default="BOUNDED_SAMPLE",
                    advanced=True,
                ),
            ],
            required_modules=["scripts.ops.confenge_commercial_target_router"],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase=(
                "Confirmo a geração local combinada (fornecedores + órgãos), sem envio automático."
            ),
            parse_result=default_parse,
            timeout_sec=7200,
            output_roots=["output/confenge-commercial", "artifacts", "output"],
        ),
        # ── Process documents ──────────────────────────────────
        Capability(
            id="process_documents.discover",
            name="Discovery documental",
            description="Discovery cadastral de entidades para documentos de processos.",
            category="process_documents",
            argv_builder=lambda p: python_m("scripts.process_documents", "discover"),
            required_modules=["scripts.process_documents"],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase="CONFIRMO",
            parse_result=default_parse,
            output_roots=["output/process_documents"],
        ),
        Capability(
            id="process_documents.collect",
            name="Coleta documental",
            description="Coleta live de documentos públicos (não submete propostas).",
            category="process_documents",
            argv_builder=lambda p: python_m(
                "scripts.process_documents",
                "collect",
                *(["--limit", str(p["limit"])] if p.get("limit") else []),
            ),
            params=[ParamSpec("limit", "Limite", type="int", advanced=True)],
            required_modules=["scripts.process_documents"],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase="CONFIRMO",
            parse_result=default_parse,
            output_roots=["output/process_documents"],
            timeout_sec=7200,
        ),
        Capability(
            id="process_documents.coverage",
            name="Cobertura documental",
            description="Relatório de cobertura operacional com categorias separadas.",
            category="process_documents",
            argv_builder=lambda p: python_m("scripts.process_documents", "coverage"),
            required_modules=["scripts.process_documents"],
            risk=RiskLevel.READ,
            parse_result=default_parse,
            output_roots=["output/process_documents"],
        ),
        Capability(
            id="process_documents.corpus",
            name="Corpus bid-readiness",
            description="Constrói ou valida manifest de corpus público.",
            category="process_documents",
            argv_builder=lambda p: python_m("scripts.process_documents", "build-corpus"),
            required_modules=["scripts.process_documents"],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase="CONFIRMO",
            parse_result=default_parse,
        ),
        Capability(
            id="process_documents.show",
            name="Consultar documentos",
            description="Mostra documentos por processo/edital/entidade.",
            category="process_documents",
            argv_builder=lambda p: python_m(
                "scripts.workspace",
                "process-documents",
                "show",
                str(p.get("query") or ""),
                "--json",
            ),
            params=[ParamSpec("query", "Processo/edital/entidade", required=True)],
            required_modules=["scripts.workspace"],
            risk=RiskLevel.READ,
            parse_result=default_parse,
        ),
        Capability(
            id="process_documents.incremental",
            name="Incremental documental",
            description="Atualização incremental de documentos.",
            category="process_documents",
            argv_builder=lambda p: python_m("scripts.process_documents", "incremental"),
            required_modules=["scripts.process_documents"],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase="CONFIRMO",
            parse_result=default_parse,
        ),
        # ── Ops ────────────────────────────────────────────────
        Capability(
            id="ops.health",
            name="Saúde operacional",
            description="Health check local do ambiente e componentes.",
            category="ops",
            argv_builder=lambda p: python_m("scripts.ops.health"),
            required_modules=["scripts.ops.health"],
            risk=RiskLevel.READ,
            parse_result=default_parse,
        ),
        Capability(
            id="ops.source_health",
            name="Saúde das fontes",
            description="Status de fontes de dados (opportunity intel / crawl).",
            category="ops",
            argv_builder=lambda p: python_m("scripts.opportunity_intel.cli", "source-health"),
            required_modules=["scripts.opportunity_intel.cli"],
            risk=RiskLevel.READ,
            parse_result=default_parse,
        ),
        Capability(
            id="ops.timer_status",
            name="Status de timers",
            description="Lista timers/systemd relevantes se acessíveis; senão degrada.",
            category="ops",
            argv_builder=lambda p: _timer_status_argv(),
            risk=RiskLevel.READ,
            parse_result=default_parse,
            fixture=False,
            required_modules=[],
        ),
        Capability(
            id="ops.soak_status",
            name="Status de soak",
            description="Lê tracker/status de soak se presente (somente leitura).",
            category="ops",
            argv_builder=lambda p: python_m("scripts.ops.campaign_soak_tracker", "--status"),
            required_modules=["scripts.ops.campaign_soak_tracker"],
            risk=RiskLevel.READ,
            parse_result=default_parse,
            expected_pr="campaign_soak_tracker",
        ),
        Capability(
            id="ops.recent_runs",
            name="Execuções recentes",
            description="Lista saídas recentes em output/ (metadados locais).",
            category="ops",
            argv_builder=lambda p: _recent_runs_argv(),
            risk=RiskLevel.READ,
            parse_result=default_parse,
        ),
        # ── DOD ────────────────────────────────────────────────
        Capability(
            id="dod.status",
            name="Status DOD",
            description="Progresso do DOD Convergence (somente leitura).",
            category="dod",
            argv_builder=lambda p: [str(REPO_ROOT / "tools" / "dod_controller.py"), "status", "--json"],
            risk=RiskLevel.READ,
            parse_result=default_parse,
            docs=["DOD.md", "docs/ops/dod-convergence.md"],
        ),
        Capability(
            id="dod.item.show",
            name="Item DOD",
            description="Mostra item do controller. Não aceita automaticamente.",
            category="dod",
            argv_builder=lambda p: [
                str(REPO_ROOT / "tools" / "dod_controller.py"),
                "report",
                "--json",
            ],
            params=[ParamSpec("item_id", "ID do item", required=False, advanced=True)],
            risk=RiskLevel.READ,
            parse_result=default_parse,
        ),
        # ── Guided consulting workflows (outcome-first) ────────
        # Executed in-process by JobRunner (not via arbitrary shell).
        # argv_builder returns a marker list for audit only.
        # ── Consulting chain (edital / budget / acervo / bid readiness) ──
        Capability(
            id="consulting.edital_case.run",
            name="Análise profunda de edital (case pack)",
            description="Pipeline edital_case: ingest→analyze→report→verify com locators. Não é parecer jurídico.",
            category="consulting",
            argv_builder=lambda p: _edital_case_argv(p),
            params=[
                ParamSpec("action", "Ação", type="select", default="run",
                          choices=["run", "analyze", "report", "verify", "gate"]),
                ParamSpec("case_dir", "Diretório do case", type="path", advanced=True),
                ParamSpec("source_dir", "Fontes (PDFs/anexos)", type="path", advanced=True),
            ],
            required_modules=["scripts.edital_case"],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase="Confirmo triagem técnica local de edital (sem submissão).",
            output_roots=["output", "data/command_center"],
            parse_result=default_parse,
            timeout_sec=3600,
        ),
        Capability(
            id="consulting.budget_audit.run",
            name="Auditoria orçamentária (planilha/BDI)",
            description="budget_audit: composições, BDI, locators. Comparação oficial exige dataset REAL_CASE_PROVEN.",
            category="consulting",
            argv_builder=lambda p: _budget_audit_argv(p),
            params=[
                ParamSpec("action", "Ação", type="select", default="run",
                          choices=["run", "audit", "references", "report", "verify"]),
                ParamSpec("case_dir", "Diretório do case", type="path", advanced=True),
                ParamSpec("source", "Planilha/fonte", type="path", advanced=True),
            ],
            required_modules=["scripts.budget_audit"],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase="Confirmo auditoria orçamentária local.",
            output_roots=["output", "data/command_center"],
            parse_result=default_parse,
            timeout_sec=3600,
        ),
        Capability(
            id="consulting.technical_acervo.match",
            name="Consultar acervo técnico EXTRA",
            description="Match de requisito vs data/extra_technical_acervo.json (fonte canônica). Sem somatório default.",
            category="consulting",
            argv_builder=lambda p: _acervo_argv(p),
            params=[
                ParamSpec("action", "Ação", type="select", default="match",
                          choices=["match", "search", "inventory", "list", "show"]),
                ParamSpec("service", "Serviço / objeto", required=False, example="pavimentacao"),
                ParamSpec("quantity", "Quantidade", type="float", advanced=True),
                ParamSpec("unit", "Unidade", default="m2", advanced=True),
                ParamSpec("allow_sum", "Permitir somatório", type="bool", default=False, advanced=True),
                ParamSpec("query", "Busca livre", advanced=True),
                ParamSpec("id", "ID documento", advanced=True),
            ],
            required_modules=["scripts.technical_acervo"],
            risk=RiskLevel.READ,
            parse_result=default_parse,
            output_roots=["data/command_center"],
        ),
        Capability(
            id="consulting.bid_readiness.run",
            name="Bid readiness (revisão humana)",
            description="Monta dossier de readiness. Nunca READY_TO_SUBMIT. Match técnico via technical_acervo.",
            category="consulting",
            argv_builder=lambda p: _bid_readiness_argv(p),
            params=[
                ParamSpec("action", "Ação", type="select", default="run",
                          choices=["run", "verify", "report", "validate", "match"]),
                ParamSpec("case_dir", "Diretório do case", type="path", advanced=True),
                ParamSpec("requirements", "requirements.json", type="path", advanced=True),
                ParamSpec("documents_dir", "Pasta de documentos", type="path", advanced=True),
            ],
            required_modules=["scripts.bid_readiness", "scripts.technical_acervo"],
            risk=RiskLevel.HUMAN_DECISION,
            requires_confirmation=True,
            confirmation_phrase="Confirmo geração de package para REVISÃO HUMANA (sem submissão).",
            output_roots=["output", "data/command_center"],
            parse_result=default_parse,
            timeout_sec=3600,
        ),
        *_workflow_capabilities(),
    ]
    return caps


def _workflow_marker(workflow_id: str) -> Callable[[dict[str, Any]], list[str]]:
    def _builder(params: dict[str, Any]) -> list[str]:
        import sys

        # Marker argv for audit trail; JobRunner intercepts workflow.* ids.
        return [sys.executable, "-m", "scripts.command_center.workflows.cli_entry", workflow_id]

    return _builder


def _workflow_capabilities() -> list[Capability]:
    """Outcome-first workflows — path-free defaults; fixture-backed when live data absent."""
    conf = "Confirmo a geração local de entregáveis (sem envio automático de mensagens)."
    return [
        Capability(
            id="workflow.extra.opportunities",
            name="Encontrar oportunidades para a Extra",
            description="Fluxo guiado: shortlist, PDF executivo, workbook e fila de revisão.",
            category="workflow",
            argv_builder=_workflow_marker("workflow.extra.opportunities"),
            params=[
                ParamSpec("period_days", "Período (dias)", type="int", default=7),
                ParamSpec("max_shortlist", "Tamanho da shortlist", type="int", default=15),
                ParamSpec(
                    "data_mode",
                    "Modo de execução",
                    type="select",
                    default="FIXTURE",
                    choices=["REAL", "FIXTURE"],
                    description="REAL=pipelines canônicos; FIXTURE=demonstração explícita.",
                ),
                ParamSpec(
                    "use_fixture",
                    "Atalho: dados de demonstração",
                    type="bool",
                    default=True,
                    advanced=True,
                    description="true→FIXTURE, false→REAL. Prefira data_mode.",
                ),
                ParamSpec(
                    "output_profile",
                    "Perfil de saída",
                    type="select",
                    default="CLIENT_READY",
                    choices=["INTERNAL_ANALYSIS", "CLIENT_READY", "AUDIT_EVIDENCE"],
                    advanced=True,
                ),
            ],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase=conf,
            parse_result=default_parse,
            output_roots=["data/command_center", "output"],
            timeout_sec=7200,
        ),
        Capability(
            id="workflow.confenge.suppliers",
            name="Encontrar empresas com potencial comercial",
            description="Fluxo guiado CONFENGE fornecedores com cobertura de cadastro e entregáveis.",
            category="workflow",
            argv_builder=_workflow_marker("workflow.confenge.suppliers"),
            params=[
                ParamSpec("uf", "UF", default="SC"),
                ParamSpec("max_companies", "Quantidade (Top N)", type="int", default=10),
                ParamSpec(
                    "population_mode",
                    "Abrangência",
                    type="select",
                    default="BOUNDED_SAMPLE",
                    choices=["BOUNDED_SAMPLE", "FULL_POPULATION"],
                ),
                ParamSpec(
                    "data_mode",
                    "Modo de execução",
                    type="select",
                    default="FIXTURE",
                    choices=["REAL", "FIXTURE"],
                ),
                ParamSpec(
                    "use_fixture",
                    "Atalho: dados de demonstração",
                    type="bool",
                    default=True,
                    advanced=True,
                ),
            ],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase=conf,
            parse_result=default_parse,
            output_roots=["data/command_center", "output"],
            timeout_sec=7200,
        ),
        Capability(
            id="workflow.confenge.public_agencies",
            name="Encontrar órgãos que podem precisar de serviços técnicos",
            description="Fluxo guiado de órgãos públicos com classificações preliminares revisáveis.",
            category="workflow",
            argv_builder=_workflow_marker("workflow.confenge.public_agencies"),
            params=[
                ParamSpec("uf", "UF", default="SC"),
                ParamSpec("max_leads", "Quantidade máxima", type="int", default=10),
                ParamSpec(
                    "mode",
                    "Modalidade",
                    type="select",
                    default="REACTIVE_OPPORTUNITY",
                    choices=["REACTIVE_OPPORTUNITY", "PROACTIVE_INSTITUTIONAL_PROSPECT"],
                ),
                ParamSpec(
                    "data_mode",
                    "Modo de execução",
                    type="select",
                    default="FIXTURE",
                    choices=["REAL", "FIXTURE"],
                ),
                ParamSpec(
                    "use_fixture",
                    "Atalho: dados de demonstração",
                    type="bool",
                    default=True,
                    advanced=True,
                ),
            ],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase=conf,
            parse_result=default_parse,
            output_roots=["data/command_center", "output"],
            timeout_sec=7200,
        ),
        Capability(
            id="workflow.process_documents",
            name="Analisar documentos de processos e editais",
            description="Fluxo guiado: cobertura documental, PDFs no navegador, índice XLSX.",
            category="workflow",
            argv_builder=_workflow_marker("workflow.process_documents"),
            params=[
                ParamSpec("query", "Processo, edital, entidade ou objeto", default="demo-processo-001", required=True),
                ParamSpec(
                    "data_mode",
                    "Modo de execução",
                    type="select",
                    default="FIXTURE",
                    choices=["REAL", "FIXTURE"],
                ),
                ParamSpec(
                    "use_fixture",
                    "Atalho: acervo de demonstração",
                    type="bool",
                    default=True,
                    advanced=True,
                ),
            ],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase=conf,
            parse_result=default_parse,
            output_roots=["data/command_center", "output"],
            timeout_sec=7200,
        ),
        Capability(
            id="workflow.edital_case",
            name="Análise técnica de edital",
            description="Fluxo consultivo: documentos → exigências → análise com evidência.",
            category="workflow",
            argv_builder=_workflow_marker("workflow.edital_case"),
            params=[
                ParamSpec("case_id", "ID do caso", default="cc-edital-case"),
                ParamSpec(
                    "source",
                    "Arquivo/pasta de documentos",
                    default="tests/edital_case/fixtures/sample_edital.pdf",
                ),
                ParamSpec(
                    "data_mode",
                    "Modo de execução",
                    type="select",
                    default="FIXTURE",
                    choices=["REAL", "FIXTURE"],
                ),
                ParamSpec(
                    "use_fixture",
                    "Atalho: dados de demonstração",
                    type="bool",
                    default=True,
                    advanced=True,
                ),
            ],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase=conf,
            parse_result=default_parse,
            output_roots=["data/command_center", "output"],
            timeout_sec=7200,
        ),
        Capability(
            id="workflow.budget_audit",
            name="Auditoria de orçamento",
            description="Fluxo consultivo: planilha → aritmética/BDI → findings.",
            category="workflow",
            argv_builder=_workflow_marker("workflow.budget_audit"),
            params=[
                ParamSpec("case_id", "ID do caso", default="cc-budget-audit"),
                ParamSpec(
                    "source",
                    "Arquivo de orçamento",
                    default="tests/budget_audit/fixtures/operational_public_style_budget.xlsx",
                ),
                ParamSpec(
                    "data_mode",
                    "Modo de execução",
                    type="select",
                    default="FIXTURE",
                    choices=["REAL", "FIXTURE"],
                ),
                ParamSpec(
                    "use_fixture",
                    "Atalho: dados de demonstração",
                    type="bool",
                    default=True,
                    advanced=True,
                ),
            ],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase=conf,
            parse_result=default_parse,
            output_roots=["data/command_center", "output"],
            timeout_sec=7200,
        ),
        Capability(
            id="workflow.technical_acervo",
            name="Consulta ao acervo técnico",
            description="Fluxo consultivo: match de serviço/quantidade no acervo canônico.",
            category="workflow",
            argv_builder=_workflow_marker("workflow.technical_acervo"),
            params=[
                ParamSpec("service", "Serviço", default="alvenaria", required=True),
                ParamSpec("qty", "Quantidade", type="int", default=100),
                ParamSpec("unit", "Unidade", default="m2"),
                ParamSpec(
                    "data_mode",
                    "Modo de execução",
                    type="select",
                    default="FIXTURE",
                    choices=["REAL", "FIXTURE"],
                ),
            ],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase=conf,
            parse_result=default_parse,
            output_roots=["data/command_center", "output"],
            timeout_sec=1800,
        ),
        Capability(
            id="workflow.bid_readiness",
            name="Bid readiness",
            description="Fluxo consultivo: exigências × documentos × acervo → revisão humana.",
            category="workflow",
            argv_builder=_workflow_marker("workflow.bid_readiness"),
            params=[
                ParamSpec("case_id", "ID do caso", default="cc-bid-readiness"),
                ParamSpec(
                    "requirements",
                    "Arquivo de requisitos",
                    default="scripts/bid_readiness/fixtures/golden/requirements.json",
                ),
                ParamSpec(
                    "documents",
                    "Pasta de documentos",
                    default="scripts/bid_readiness/fixtures/golden/documents",
                ),
                ParamSpec(
                    "data_mode",
                    "Modo de execução",
                    type="select",
                    default="FIXTURE",
                    choices=["REAL", "FIXTURE"],
                ),
                ParamSpec(
                    "use_fixture",
                    "Atalho: dados de demonstração",
                    type="bool",
                    default=True,
                    advanced=True,
                ),
            ],
            risk=RiskLevel.WRITE_LOCAL,
            requires_confirmation=True,
            confirmation_phrase=conf,
            parse_result=default_parse,
            output_roots=["data/command_center", "output"],
            timeout_sec=7200,
        ),
    ]


def _weekly_argv(p: dict[str, Any]) -> list[str]:
    argv = python_m("scripts.ops.weekly_cycle")
    if p.get("strict", True):
        argv.append("--strict")
    else:
        argv.append("--no-strict")
    if p.get("skip_collect"):
        argv.append("--skip-collect")
    if p.get("offline"):
        argv.append("--offline")
    if p.get("limit") is not None:
        argv.extend(["--limit", str(int(p["limit"]))])
    if p.get("output_dir"):
        argv.extend(["--output-dir", str(p["output_dir"])])
    return argv


def _actionable_argv(p: dict[str, Any]) -> list[str]:
    # Prefer dedicated module; fall back shape matches decision loop inputs
    return python_m(
        "scripts.ops.extra_actionable",
        "run",
        "--weekly-dir",
        str(p["weekly_input"]),
        "--out",
        str(p["out"]),
    )


def _registry_argv(action: str, p: dict[str, Any]) -> list[str]:
    base = python_m("scripts.company_registry")
    if action == "lookup":
        return base + ["lookup", str(p.get("cnpj") or "")]
    if action == "coverage":
        return base + ["coverage"]
    return base + ["health"]


def _commercial_router_argv(target: str, p: dict[str, Any]) -> list[str]:
    """Canonical commercial entry: target_router (suppliers | public-agencies | all).

    Suppliers path goes through official registry precheck when
    CONFENGE_REQUIRE_OFFICIAL_REGISTRY is on (router default).
    """
    if target not in {"suppliers", "public-agencies", "all"}:
        raise ValueError(f"target comercial inválido: {target}")
    argv = python_m("scripts.ops.confenge_commercial_target_router", "--target", target)
    run_mode = p.get("run_mode") or "DRY_RUN"
    argv.extend(["--run-mode", str(run_mode)])
    if p.get("out"):
        argv.extend(["--out", str(p["out"])])
    if p.get("max_contracts") is not None:
        argv.extend(["--max-contracts", str(int(p["max_contracts"]))])
    if p.get("population_mode"):
        argv.extend(["--population-mode", str(p["population_mode"])])
    # public-agency specific
    uf = p.get("uf") or p.get("state")
    if uf:
        argv.extend(["--uf", str(uf)])
    if p.get("max_public_agency_leads") is not None:
        argv.extend(["--max-public-agency-leads", str(int(p["max_public_agency_leads"]))])
    elif p.get("max_items") is not None:
        # back-compat with older param name from UI fixtures
        argv.extend(["--max-public-agency-leads", str(int(p["max_items"]))])
    if p.get("public_agency_mode"):
        argv.extend(["--public-agency-mode", str(p["public_agency_mode"])])
    if p.get("public_agency_out"):
        argv.extend(["--public-agency-out", str(p["public_agency_out"])])
    if p.get("public_agency_profile"):
        argv.extend(["--public-agency-profile", str(p["public_agency_profile"])])
    if p.get("as_of"):
        argv.extend(["--as-of", str(p["as_of"])])
    if p.get("skip_migrations"):
        argv.append("--skip-migrations")
    if p.get("skip_persist"):
        argv.append("--skip-persist")
    return argv


def _timer_status_argv() -> list[str]:
    # Read-only systemctl list if available; else python print degraded
    import shutil
    import sys

    if shutil.which("systemctl"):
        return [
            "systemctl",
            "list-timers",
            "extra-*",
            "pncp-*",
            "--no-pager",
        ]
    return [
        sys.executable,
        "-c",
        "print('TIMERS_UNAVAILABLE'); print('systemctl não disponível neste host (somente leitura).');",
    ]


def _recent_runs_argv() -> list[str]:
    import sys

    code = r"""
from pathlib import Path
import json
root = Path('output')
items = []
if root.exists():
    for p in sorted(root.rglob('*'), key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True):
        if p.is_file() and p.suffix in {'.json', '.md', '.csv', '.xlsx'} and 'node_modules' not in p.parts:
            items.append({'path': str(p), 'bytes': p.stat().st_size, 'mtime': p.stat().st_mtime})
            if len(items) >= 40:
                break
print(json.dumps({'recent': items}, ensure_ascii=False, indent=2))
"""
    return [sys.executable, "-c", code]


def _edital_case_argv(p: dict[str, Any]) -> list[str]:
    from pathlib import Path

    from scripts.command_center.adapters.consulting_chain import EditalCaseAdapter
    out = Path(str(p.get("case_dir") or "data/command_center/edital_case"))
    return EditalCaseAdapter().build_argv(p, out_dir=out)


def _budget_audit_argv(p: dict[str, Any]) -> list[str]:
    from pathlib import Path

    from scripts.command_center.adapters.consulting_chain import BudgetAuditAdapter
    out = Path(str(p.get("case_dir") or "data/command_center/budget_audit"))
    return BudgetAuditAdapter().build_argv(p, out_dir=out)


def _acervo_argv(p: dict[str, Any]) -> list[str]:
    from pathlib import Path

    from scripts.command_center.adapters.consulting_chain import TechnicalAcervoAdapter
    return TechnicalAcervoAdapter().build_argv(p, out_dir=Path("data/command_center"))


def _bid_readiness_argv(p: dict[str, Any]) -> list[str]:
    from pathlib import Path

    from scripts.command_center.adapters.consulting_chain import BidReadinessAdapter
    out = Path(str(p.get("case_dir") or "data/command_center/bid_readiness"))
    return BidReadinessAdapter().build_argv(p, out_dir=out)

