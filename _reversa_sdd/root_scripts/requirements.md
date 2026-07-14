# Root Scripts — CLI Entry Points e Orquestração

> Gerado pelo Writer em 2026-07-13T17:30:00Z | doc_level: completo | Base: plano-mestre-fechamento-gaps, brownfield discovery

## Visão Geral

A camada `scripts/` contém ~40 scripts Python que são os entry points do sistema — invocados por usuários (CLI manual), por systemd timers (crawlers automáticos) e por pipelines (intel, backfill). Esta camada orquestra toda a funcionalidade do sistema: desde a ingestão de dados (crawlers) até a geração de relatórios executivos (PDF/Excel), passando por monitoramento, alertas e inteligência competitiva.

## Responsabilidades

- Orquestrar pipelines multi-estágio com quality gates (intel_pipeline.py, pipeline/backfill_multi_source.py)
- Prover CLI de consulta ao DataLake PostgreSQL (local_datalake.py)
- Calcular e reportar métricas de cobertura (coverage_truth.py, consulting_readiness.py, freshness_gate.py)
- Executar radar de oportunidades (opportunity_intel/cli.py)
- Consolidar inteligência contratual (contract_intel/cli.py)
- Coletar métricas operacionais e disparar alertas (collect-metrics.py, check-alerts.py, notify.py)
- Gerar relatórios panorâmicos e semanais (reports/panorama.py, reports/coverage_weekly.py)
- Dashboard de saúde do sistema (health-dashboard.py, health_check.py, healthcheck.py)
- Pipeline B2G setorial (demo_b2g_setorial.py, generate-report-b2g.py)
- Coleta de dados cadastrais (collect-report-data.py, collect-sicaf.py)
- Scripts utilitários de infraestrutura (apply-migrations.sh, backup-database.sh, ci-check.sh)
- **PENDENTE**: Comando `scripts/consulting/cli.py build-delivery` (plano-mestre §16, EPIC P1-03)

## Regras de Negócio

- R17: Freshness gate bloqueia uso de dados se fonte crítica estiver stale (pncp > 6h, contracts > 24h) 🟢
- R18: Cobertura mínima de 95% para considerar readiness — exit code 2 se abaixo 🟢
- R19: Manifesto de cobertura por capability (não métrica global única) 🟢
- R20: Source blockers documentam fontes que não executam no ambiente atual (doe_sc, dom_sc, pcp, sc_compras, transparencia) 🟢
- R21: Pipeline intel usa 5 quality gates com auto-fix entre estágios 🟢
- R22: Radar de oportunidades opera apenas com snapshot PNCP confirmado (sem registros órfãos) 🟡
- R23: Dados brutos imutáveis (gzip, SHA-256, run_id) — uma vez persistidos, não podem ser alterados 🟡
- R24: Notificações de alerta enviadas via SMTP e webhook (Slack/Discord) configuráveis por env vars 🟢
- R25: Build-delivery (P1-03) deve emitir manifest com run_id, git SHA, seed SHA e schema fingerprint 🔴 LACUNA — comando não implementado

## Requisitos Funcionais

| ID | Requisito | Prioridade | Fonte |
|----|-----------|-----------|-------|
| RF-RS01 | Executar pipeline intel de 7 estágios: collect, enrich, llm_gate, extract_docs, analyze, excel, report | Must | `intel_pipeline.py:739-1184` |
| RF-RS02 | Aplicar 5 quality gates (cobertura, cadastral, ruído, conteúdo, recomendação) com auto-fix | Must | `intel_pipeline.py:200-700` |
| RF-RS03 | Buscar licitações no DataLake local com filtros UF, modalidade, dias, palavras-chave | Must | `local_datalake.py:cmd_search()` |
| RF-RS04 | Exibir dados de fornecedor por CNPJ (contratos, pricing, competidores) | Must | `local_datalake.py:cmd_supplier()` |
| RF-RS05 | Exibir estatísticas do DataLake (total registros, fontes, cobertura) | Must | `local_datalake.py:cmd_stats()` |
| RF-RS06 | Gerar relatório de cobertura truth: entities, sources, evidence | Must | `coverage_truth.py:report()` |
| RF-RS07 | Executar freshness gate para fontes críticas (pncp >6h, contracts >24h) | Must | `freshness_gate.py:evaluate_source()` |
| RF-RS08 | Calcular readiness consulting 95%+ com manifest e gaps | Must | `consulting_readiness.py:main()` |
| RF-RS09 | Listar oportunidades abertas com filtros (status, UF, modalidade) | Should | `opportunity_intel/cli.py:cmd_list()` |
| RF-RS10 | Executar radar QW-01 com cobertura e manifest auditável | Should | `opportunity_intel/cli.py:cmd_radar()` |
| RF-RS11 | Consolidar histórico contratual 3 anos e ranking de fornecedores | Must | `contract_intel/cli.py:cmd_historico()` |
| RF-RS12 | Listar contratos vincendos (90-180 dias) | Should | `contract_intel/cli.py:cmd_ativos()` |
| RF-RS13 | Coletar métricas operacionais: crawl, cobertura, backup, alertas | Should | `collect-metrics.py:collect_all()` |
| RF-RS14 | Verificar condições críticas e disparar notificações | Must | `check-alerts.py:main()` |
| RF-RS15 | Enviar notificações via SMTP e webhook Slack/Discord | Must | `notify.py:dispatch()` |
| RF-RS16 | Exibir dashboard de saúde do sistema (DB, disco, crawlers, backup) | Should | `health-dashboard.py:main()` |
| RF-RS17 | Executar backfill multi-source com iterações até estabilização da cobertura | Should | `pipeline/backfill_multi_source.py:run_pipeline()` |
| RF-RS18 | Gerar panorama de mercado (PDF + Excel) com volume, modalidades, UFs | Should | `reports/panorama.py:main()` |
| RF-RS19 | Gerar relatório semanal de cobertura (PDF executivo + Excel detalhado) | Should | `reports/coverage_weekly.py:main()` |
| RF-RS20 | Coletar dados cadastrais de empresas (OpenCNPJ, BrasilAPI, IBGE) | Should | `collect-report-data.py:main()` |
| RF-RS21 | Coletar dados SICAF de fornecedores | Should | `collect-sicaf.py:main()` |
| RF-RS22 | Executar comando unificado `build-delivery` com freeze universe, freshness, readiness, datasets, Excel, PDF, manifest | Must | 🔴 LACUNA — `scripts/consulting/cli.py` não existe |
| RF-RS23 | Executar sistema de alerts/resilience: degradation tracking, circuit breaker | Should | `degradation.py:track_degradation()` |
| RF-RS24 | Gerar relatórios B2G setoriais com PDF e Excel | Could | `demo_b2g_setorial.py`, `generate-report-b2g.py` |

## Requisitos Não Funcionais

| Tipo | Requisito | Evidência | Confiança |
|------|----------|----------|-----------|
| Performance | Pipeline intel: timeouts configuráveis (collect=1800s, enrich=300s, llm=120s, extract=600s) | `intel_pipeline.py:57-62` | 🟢 |
| Performance | DataLake CLI queries com índices PostgreSQL (sem full scan em milhões de registros) | `local_datalake.py` usa psycopg2 | 🟡 |
| Disponibilidade | 20+ systemd timers para crawlers automáticos com schedules definidos | `deploy/systemd/*.timer` | 🟢 |
| Disponibilidade | Freshness gate com SLA configurável (pncp=6h, contracts=24h) | `freshness_gate.py:CRITICAL_SOURCES` | 🟢 |
| Disponibilidade | Alertas com 3 níveis: pass (0), warning (1), critical (2) | `check-alerts.py:exit codes` | 🟢 |
| Segurança | DSN via env var `LOCAL_DATALAKE_DSN` — hardcoded default apenas para dev local | Todos os scripts | 🟢 |
| Manutenibilidade | Source registry central (`scripts/crawl/registry.py`) como fonte única de verdade | `backfill_multi_source.py:43` | 🟢 |
| Consistência | Nomenclatura de scripts em DUAS convenções (kebab-case E snake_case) — causa confusão | `intel-collect.py` vs `intel_collect.py`, `collect-report-data.py` vs `collect_report_data.py` | 🔴 |
| Consistência | Múltiplos health checks duplicados (health_check.py, healthcheck.py, health-dashboard.py) | Três scripts com sobreposição | 🔴 |
| Portabilidade | Scripts assumem PostgreSQL local — sem abstração para outros backends | DSN hardcoded em todos | 🟡 |
| Resiliência | Degradation tracking e circuit breaker para falhas de crawler | `degradation.py`, `circuit_breaker.py` | 🟢 |

## Critérios de Aceitação

```gherkin
Cenário: Pipeline intel executa 7 estágios com quality gates
Dado CNPJ "01721078000168" com UFs=["SC"] e dias=90
Quando intel_pipeline.py executa via CLI
Então 7 estágios executam sequencialmente
E 5 quality gates retornam PASS
E JSON final gerado em data/intel/

Cenário: Freshness gate bloqueia readiness com dados stale
Dado fonte "pncp" sem execução nas últimas 6 horas
Quando freshness_gate.py executa
Então exit code = 2
E source_fresh = False no output JSON

Cenário: Backfill multi-source atinge estabilização
Dado todas as fontes configuradas no registry
Quando pipeline/backfill_multi_source.py executa com --all-sources
Então cobertura incrementa a cada iteração
E pipeline para após 2 execuções sem novas entidades

Cenário: Build-delivery gera artefatos completos (P1-03)
Dado seed "Extra - alvos de licitação. R-0.xlsx" e profile configurado
Quando scripts/consulting/cli.py build-delivery executa
Então universo congelado, freshness verificado, readiness executado
E Excel gerado com 14 planilhas
E PDF gerado com dados reconciliados
E manifest emitido com run_id, git SHA, seed SHA
🔴 LACUNA: Comando não existe — EPIC P1-03 não implementado

Cenário: Check de alertas detecta disco cheio
Dado uso de disco > 90%
Quando check-alerts.py executa
Então exit code = 2
E notificação enviada via notify.py (SMTP ou webhook)
```

## Prioridade MoSCoW

| Prioridade | Requisitos | Esforço estimado |
|-----------|-----------|-----------------|
| **Must** | RF-RS01 a RF-RS08, RF-RS11, RF-RS14, RF-RS15, RF-RS22 | Implementado parcialmente (RF-RS22 não existe) |
| **Should** | RF-RS09, RF-RS10, RF-RS12, RF-RS13, RF-RS16 a RF-RS21 | 5-8 dias |
| **Could** | RF-RS23, RF-RS24 | 1-2 dias |
| **Won't** | — | — |

## Legacy Intel Pipeline

> **Migrado de `intel/` para `root_scripts/` em 2026-07-13.**

O pipeline Intel legado (7 estagios, 5 quality gates) e composto por scripts que residem em `scripts/` top-level, nunca em um submodulo `intel/` separado. Estes scripts coexistem em duas convencoes de nomenclatura (kebab-case e snake_case), conforme documentado na secao de NFR (consistencia).

### Scripts do Pipeline Legado

| Script | Nomenclatura | Role |
|--------|-------------|------|
| `intel_pipeline.py` | snake_case | Orquestrador principal (7 estagios) |
| `intel-collect.py` | kebab-case | Coleta de licitacoes PNCP (12 sub-etapas) |
| `intel-enrich.py` | kebab-case | Enriquecimento cadastral e geografico |
| `intel-validate.py` | kebab-case | Validacao semantica (4 hard-incompatible patterns) |
| `intel-analyze.py` | kebab-case | Analise LLM com GPT-4.1-nano (21 campos) |
| `intel-extract-docs.py` | kebab-case | Extracao de texto de documentos (PDF/ZIP/XLSX) |
| `intel-excel.py` | kebab-case | Geracao de Excel (4 planilhas, 31 colunas) |
| `intel-report.py` | kebab-case | Geracao de PDF executivo (9 secoes) |
| `intel_collect.py` | snake_case | Duplicata de nomenclatura (collect) |
| `intel_excel.py` | snake_case | Duplicata de nomenclatura (excel) |
| `intel_validate.py` | snake_case | Duplicata de nomenclatura (validate) |
| `intel_report.py` | snake_case | Duplicata de nomenclatura (report) |
| `intel_llm_gate.py` | snake_case | Gate LLM (separado) |
| `intel_sector_loader.py` | snake_case | Loader de setores (separado) |

### Documentacao Historica

A documentacao original do pipeline Intel permanece em `_reversa_sdd/intel/` como registro historico:
- `_reversa_sdd/intel/requirements.md` — Requisitos funcionais e nao funcionais originais
- `_reversa_sdd/intel/design.md` — Design original
- `_reversa_sdd/intel/tasks.md` — Tarefas originais
- `_reversa_sdd/intel/README.md` — Nota de migracao

### Substituo Funcional

O pipeline Intel legado foi substituido pelo modulo `opportunity_intel/` (radar de oportunidades QW-01), documentado em `_reversa_sdd/opportunity_intel/`.

## Rastreabilidade de Código

| Script | Linhas | Role principal | Invocado por |
|--------|--------|---------------|-------------|
| `intel_pipeline.py` | 1.269 | Orquestrador pipeline intel 7 estágios | CLI manual |
| `local_datalake.py` | 683 | CLI consulta DataLake | CLI manual |
| `coverage_truth.py` | 944 | Métricas de cobertura auditáveis | CLI manual |
| `consulting_readiness.py` | 2.110 | Readiness assessment | CLI manual |
| `freshness_gate.py` | 294 | Gate de freshness | CLI manual |
| `collect-metrics.py` | 439 | Coleta métricas operacionais | systemd timer |
| `check-alerts.py` | 553 | Verificação de alertas críticos | systemd timer |
| `notify.py` | 300 | Disparo de notificações | check-alerts.py |
| `health-dashboard.py` | 472 | Dashboard HTML de saúde | CLI manual |
| `opportunity_intel/cli.py` | 685 | Radar de oportunidades | CLI manual |
| `contract_intel/cli.py` | 1.267 | Inteligência contratual | CLI manual |
| `reports/panorama.py` | 356 | Panorama de mercado | CLI manual |
| `reports/coverage_weekly.py` | 1.325 | Relatório semanal cobertura | systemd timer |
| `pipeline/backfill_multi_source.py` | 871 | Backfill multi-fontes | CLI manual |
| `collect-report-data.py` | 11.064 | Coleta dados cadastrais | CLI manual |
| `collect-sicaf.py` | — | Coleta SICAF | CLI manual |
| `degradation.py` | 22 | Tracking de degradação | Import lib |
| `health_check.py` | 173 | Check infraestrutura | CLI/systemd |
| `healthcheck.py` | 223 | Check saúde (duplicado) | CLI/systemd |
| `demo_b2g_setorial.py` | — | Demonstração B2G setorial | CLI manual |
| `generate-report-b2g.py` | — | Relatório B2G | CLI manual |
| `_pt_accents.py` | — | Helper acentos PT-BR | Import lib |
| `exceptions.py` | — | Exceções customizadas | Import lib |
| `metrics.py` | 23 | Métricas genéricas | Import lib |
| `middleware.py` | — | Middleware (não utilizado?) | Import lib |
| `pncp_client.py` | — | Cliente HTTP PNCP | Import lib |
| `rate_limiter.py` | — | Rate limiter adaptativo | Import lib |
| `redis_pool.py` | — | Pool de conexões Redis | Import lib |
| `report_dedup.py` | — | Dedup de relatórios | Import lib |
| `supabase_client.py` | — | Cliente Supabase | Import lib |
| `validate-report-data.py` | — | Validação dados relatório | Import lib |
| `crawl/monitor.py` | 1.755 | Orquestrador de crawlers | systemd timer + CLI |
