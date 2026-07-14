# Root Scripts — Tasks

> Gerado pelo Writer em 2026-07-13T17:30:00Z | doc_level: completo

## Tarefas de Reimplementação

| # | Tarefa | Fonte | Critério de Pronto | Confiança |
|---|--------|-------|-------------------|-----------|
| T-RS01 | Implementar pipeline orchestrator intel: CLI argparse, 7 estágios como subprocess, 5 quality gates com auto-fix | `intel_pipeline.py:739-1184` | Pipeline executa 7 estágios sequenciais com timeouts configuráveis; gates retornam PASS/FAIL | 🟢 |
| T-RS02 | Implementar gate de cobertura (G1): API status, total > 0, UF coverage | `intel_pipeline.py:215-284` | Bloqueia pipeline se cobertura insuficiente | 🟢 |
| T-RS03 | Implementar gate cadastral (G2): sanctions, SICAF, enrichment >= 50% | `intel_pipeline.py:286-360` | Bloqueia se empresa sancionada ou sem enriquecimento mínimo | 🟢 |
| T-RS04 | Implementar gate de ruído (G3): compat ratio 5-80%, zero needs_llm_review | `intel_pipeline.py:362-444` | Filtra editais incompatíveis | 🟢 |
| T-RS05 | Implementar gate de conteúdo (G4): doc coverage >= 50%, watermark, dedup | `intel_pipeline.py:446-550` | Garante que editais tenham documentação mínima | 🟢 |
| T-RS06 | Implementar gate de recomendação (G5): remove NAO PARTICIPAR, valida 10x capacity | `intel_pipeline.py:549-720` | Top 20 limpo e ordenado por opportunity score | 🟢 |
| T-RS07 | Implementar CLI DataLake: search, supplier, pricing, competitors, stats, detail | `local_datalake.py:62-683` | 6 subcomandos funcionais com output rich table | 🟢 |
| T-RS08 | Implementar coverage truth: entidades por raio, cobertura por fonte, evidence ledger | `coverage_truth.py:1-944` | Relatório auditável por capability (bids, contracts, pricing, competition) | 🟢 |
| T-RS09 | Implementar consulting readiness: carregar universo, evidências, manifest, gaps | `consulting_readiness.py:1-2110` | Manifest com threshold 95%, exit code 2 se abaixo | 🟢 |
| T-RS10 | Implementar freshness gate: fontes críticas (pncp=6h, contracts=24h), SLA configurável | `freshness_gate.py:1-294` | 0=fresh, 2=stale | 🟢 |
| T-RS11 | Implementar collect-metrics: crawl metrics, coverage, backup, failures | `collect-metrics.py:1-439` | JSON output com métricas de N dias | 🟢 |
| T-RS12 | Implementar check-alerts: falhas consecutivas, disco, DB, storage, backup, API keys | `check-alerts.py:1-553` | 3 níveis de severidade; integração com notify.py | 🟢 |
| T-RS13 | Implementar notify: SMTP e webhook Slack/Discord, config por env vars | `notify.py:1-300` | Notificação enviada com subject, body, canais configuráveis | 🟢 |
| T-RS14 | Implementar health dashboard: sistema, crawl, backup, alertas | `health-dashboard.py:1-472` | Dashboard HTML com dados dos últimos N dias | 🟢 |
| T-RS15 | Implementar opportunity intel CLI: list, show, explain, coverage, source-health, update, export, radar | `opportunity_intel/cli.py:1-685` | 8 subcomandos; radar com QW-01 manifesto auditável | 🟢 |
| T-RS16 | Implementar contract intel CLI: historico 3 anos, fornecedores ranking, ativos vincendos | `contract_intel/cli.py:1-1267` | 3 subcomandos; queries PostgreSQL canônicas (migration 026) | 🟢 |
| T-RS17 | Implementar relatório panorama: volume, modalidades, UFs, monthly trends | `reports/panorama.py:1-356` | Terminal + Excel + PDF opcional | 🟢 |
| T-RS18 | Implementar relatório semanal cobertura: executive PDF + detailed Excel | `reports/coverage_weekly.py:1-1325` | Big Four aesthetic; snapshot + PDF + Excel | 🟢 |
| T-RS19 | Implementar backfill multi-source: todas as fontes em sequência, iterações até estabilização | `pipeline/backfill_multi_source.py:1-871` | Cobertura incremental até 2 execuções sem delta | 🟢 |
| T-RS20 | **IMPLEMENTAR** comando build-delivery: freeze universe, freshness, readiness, datasets, Excel 14 sheets, PDF, manifest | Plano-mestre §16 (EPIC P1-03) | `python -m scripts.consulting.cli build-delivery` gera artefatos completos com run_id, git SHA, seed SHA | 🔴 |
| T-RS21 | Padronizar nomenclatura: snake_case canônico, deprecar kebab-case | `intel-collect.py`, `intel_enrich.py`, `collect-report-data.py`, `collect_report_data.py` | Zero scripts kebab-case após migração; aliases de compatibilidade | 🔴 |
| T-RS22 | Unificar health checks: deprecar `health_check.py` e `healthcheck.py`, manter `health-dashboard.py` | `health_check.py:173`, `healthcheck.py:223` | Apenas 1 script de health check; funcionalidades migradas | 🔴 |
| T-RS23 | Remover carregador de universo duplicado em consulting_readiness.py | `consulting_readiness.py` vs `scripts/lib/universe.py` | consulting_readiness.py usa exclusivamente `scripts.lib.universe` | 🟡 |
| T-RS24 | Implementar reconciliação de snapshot PNCP no radar de oportunidades | `opportunity_intel/cli.py`, plano-mestre §2.2 | Radar exibe apenas registros confirmados no snapshot mais recente | 🔴 |
| T-RS25 | Centralizar DSN em config/settings.py para todos os scripts | Distribuído em 15+ scripts | `LOCAL_DATALAKE_DSN` lido de settings.py, não hardcoded | 🟡 |
| T-RS26 | Implementar testes unitários para scripts CLI entry points | Sem testes atuais | Cobertura mínima de 60% para funções críticas | 🟡 |

## Dependências entre Tarefas

```
# Core
T-RS01 (orquestrador intel) → T-RS02..T-RS06 (gates)
T-RS07 (DataLake CLI) → independente (consulta direta DB)

# Readiness
T-RS10 (freshness) → T-RS09 (readiness) → T-RS08 (coverage truth)
T-RS20 (build-delivery) → T-RS10 + T-RS09 + T-RS15 + T-RS16

# Monitoramento
T-RS11 (metrics) → T-RS12 (alerts) → T-RS13 (notify)
T-RS14 (dashboard) → T-RS11 + T-RS12

# Relatórios
T-RS17 (panorama) → independente
T-RS18 (coverage weekly) → independente
T-RS19 (backfill) → T-RS01..T-RS06 (usa crawlers)

# Qualidade
T-RS21 (nomenclatura) → refatoração transversal
T-RS22 (health unify) → refatoração local
T-RS23 (universe dedup) → T-RS09 (readiness)
T-RS24 (snapshot reconcile) → T-RS15 (radar)
T-RS25 (DSN central) → refatoração transversal
T-RS26 (testes) → após todas as implementações

# Pipeline P1-03 (EPIC completo)
T-RS20 (build-delivery) → T-RS10 + T-RS09 + T-RS08
T-RS20 → T-RS15 + T-RS16 (oportunidades + contratos)
T-RS20 → T-RS07 (DataLake para datasets)
T-RS20 → gera Excel + PDF + manifest
```

## Estimativa de Esforço

| Categoria | Tarefas | Esforço estimado |
|-----------|---------|-----------------|
| Pipeline Intel | T-RS01 a T-RS06 | 3-4 dias |
| DataLake CLI | T-RS07 | 1 dia |
| Readiness & Coverage | T-RS08 a T-RS10 | 2-3 dias |
| Monitoramento & Alertas | T-RS11 a T-RS14 | 2-3 dias |
| CLI Oportunidade & Contratos | T-RS15, T-RS16 | 2-3 dias |
| Relatórios | T-RS17, T-RS18 | 2-3 dias |
| Backfill | T-RS19 | 1-2 dias |
| **Build-Delivery (P1-03)** | **T-RS20** | **3-4 dias** |
| Refatoração & Qualidade | T-RS21 a T-RS26 | 2-3 dias |
| **Total** | **26 tarefas** | **18-26 dias** |

## Prioridade de Execução

| Fase | Tarefas | Objetivo |
|------|---------|----------|
| **P0** | T-RS01 a T-RS10 | Core funcional já implementado — testar e validar |
| **P1** | T-RS20 | EPIC P1-03 build-delivery (plano-mestre §16) |
| **P2** | T-RS11 a T-RS19 | Monitoramento, relatórios e backfill |
| **P3** | T-RS21 a T-RS26 | Refatoração, qualidade e centralização |
