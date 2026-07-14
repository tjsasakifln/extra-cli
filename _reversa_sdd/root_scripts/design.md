# Root Scripts — Design Técnico

> Gerado pelo Writer em 2026-07-13T17:30:00Z | doc_level: completo

## Arquitetura Geral

A camada `scripts/` não possui um framework unificado — cada script é um entry point Python autônomo com `if __name__ == '__main__'` e `argparse`. A orquestração entre scripts ocorre via:

1. **Subprocess calls** — `intel_pipeline.py` chama scripts-filhos como subprocessos com timeouts
2. **systemd timers** — 20+ timers invocam scripts diretamente (`ExecStart=python scripts/...`)
3. **CLI manual** — usuário invoca scripts diretamente no terminal
4. **Import direto** — scripts importam módulos de `scripts/lib/`, `config/`, e outros

```
┌─────────────────────────────────────────────────────────────────┐
│                    ROOT SCRIPTS LAYER                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐  ┌────────────────┐  ┌──────────────────┐     │
│  │ Orquestração │  │ Análise/Intel  │  │  Monitoramento   │     │
│  │              │  │                │  │                  │     │
│  │ intel_pipe.. │  │ coverage_tr..  │  │ collect-metri..  │     │
│  │ backfill_m.. │  │ consulting_r.. │  │ check-alerts.py  │     │
│  │ crawl/moni.. │  │ freshness_ga.. │  │ notify.py        │     │
│  │              │  │ local_datala.. │  │ health-dashbo..  │     │
│  └──────┬───────┘  └───────┬────────┘  └────────┬─────────┘     │
│         │                  │                     │              │
│  ┌──────┴───────┐  ┌──────┴────────┐  ┌────────┴─────────┐     │
│  │ Oportunidade │  │ Contratos     │  │ Relatórios        │     │
│  │              │  │               │  │                   │     │
│  │ opportunity_ │  │ contract_in.. │  │ reports/panorama  │     │
│  │ intel/cli.py │  │ /cli.py       │  │ reports/covera..  │     │
│  └──────────────┘  └───────────────┘  └───────────────────┘     │
│                                                                 │
│  🔴 LACUNA: scripts/consulting/cli.py (build-delivery P1-03)   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │   PostgreSQL DataLake   │
              │   (LOCAL_DATALAKE_DSN)  │
              └─────────────────────────┘
```

## Interfaces

### Interface Comum (CLI)

Todos os scripts entry point seguem o padrão:

```python
python scripts/{script}.py [subcommand] [--flags]
```

### Comandos Principais

| Script | Subcomandos | Flags principais |
|--------|------------|------------------|
| `intel_pipeline.py` | — (run único) | `--cnpj`, `--ufs`, `--dias`, `--top`, `--from-step`, `--skip-sicaf`, `--no-cache` |
| `local_datalake.py` | `search`, `supplier`, `pricing`, `competitors`, `stats`, `detail` | `--uf`, `--dias`, `--cnpj`, `--modalidades`, `--keywords`, `--pncp-id` |
| `coverage_truth.py` | `report` | `--radius-km`, `--output-dir`, `--entity-id` |
| `consulting_readiness.py` | — (run único) | `--radius-km`, `--threshold`, `--seed`, `--output-dir` |
| `freshness_gate.py` | — (run único) | `--source`, `--output-dir` |
| `collect-metrics.py` | — (run único) | `--source`, `--days`, `--summary`, `--export` |
| `check-alerts.py` | — (run único) | `--json`, `--dry-run`, `--test` |
| `notify.py` | — (run único) | `--subject`, `--body`, `--webhook-url`, `--test` |
| `health-dashboard.py` | — (run único) | `--days`, `--port` |
| `opportunity_intel/cli.py` | `list`, `show`, `explain`, `coverage`, `source-health`, `update`, `export`, `radar` | `--status`, `--uf`, `--limit`, `--source`, `--format`, `--output` |
| `contract_intel/cli.py` | `historico`, `fornecedores`, `ativos` | `--cnpj`, `--dias`, `--output` |
| `reports/panorama.py` | — (run único) | `--setor`, `--uf`, `--dias`, `--monthly`, `--output-pdf`, `--output-excel` |
| `reports/coverage_weekly.py` | — (run único) | `--date`, `--output-dir`, `--snapshot-only`, `--skip-snapshot` |
| `pipeline/backfill_multi_source.py` | — (run único) | `--all-sources`, `--sources`, `--dry-run`, `--resume` |
| 🔴 `consulting/cli.py` | `build-delivery` | `--profile`, `--seed`, `--period-years`, `--output` |

### Comando Build-Delivery (P1-03 — NÃO IMPLEMENTADO)

Conforme plano-mestre §16, o comando deve executar 8 etapas em sequência:

```python
# python -m scripts.consulting.cli build-delivery
#   --profile config/client_profiles/extra.yaml
#   --seed "Extra - alvos de licitação. R-0.xlsx"
#   --period-years 3
#   --output output/deliveries

# Etapas:
# 1. congelar universo
# 2. verificar freshness
# 3. executar readiness
# 4. gerar datasets
# 5. bloquear claims não prontos
# 6. gerar Excel (14 planilhas)
# 7. gerar PDF estruturado
# 8. emitir manifest
```

## Fluxo Principal

### Pipeline Intel (RF-RS01)

```
main() → parser args → 
  [S1] intel_collect.py (subprocess timeout=1800s) →
  [G1] gate1_cobertura() → auto-fix →
  [S2] intel_enrich.py (subprocess timeout=300s) →
  [G2] gate2_cadastral() → auto-fix →
  [S3] intel_llm_gate.py (subprocess timeout=120s) →
  [G3] gate3_ruido() → auto-fix →
  [S4] intel_extract_docs.py (subprocess timeout=600s) →
  [G4] gate4_conteudo() → auto-fix →
  [S5] intel_analyze.py --prepare (manual step) →
  [G5] gate5_recomendacao() → auto-fix →
  [S6] intel_excel.py (subprocess) →
  [S7] intel_report.py (subprocess) →
  exit(0) se todos gates PASS
```

### Backfill Multi-Source (RF-RS17)

```
main() → parse_args → run_pipeline():
  LOOP até max_iterations (3) OU estabilização:
    FOR cada source em SOURCE_ORDER:
      run_crawl(source) → crawl_source(source)
      run_matching(source) → entity matching cascade
    compute_coverage_delta()
    IF delta = 0 por 2 iterações consecutivas:
      BREAK
  Gerar relatório final de cobertura
```

### Freshness + Readiness + Coverage Truth

```
freshness_gate.py → evaluate_source() para pncp + contracts
  → output/readiness/freshness-gate.json

coverage_truth.py → load_entities_within_radius() + load_entity_coverage()
  → relatório por capability (bids, contracts, pricing, competition)

consulting_readiness.py → load_target_universe() + load_evidence()
  → coverage_manifest.json + coverage_gaps.csv
  → exit(0) se >= 95%, exit(2) se abaixo
```

## Dependências

### Entre Scripts

```
crawl/monitor.py → scripts/crawl/* (crawlers individuais)
intel_pipeline.py → intel_collect.py, intel_enrich.py, intel_llm_gate.py,
                    intel_extract_docs.py, intel_excel.py, intel_report.py
check-alerts.py → notify.py (envio de notificação)
check-alerts.py → health_check.py (infra checks)
collect-metrics.py → consulta ingestion_runs + ingestion_checkpoints
opportunity_intel/cli.py → crawl/monitor.py (update)
pipeline/backfill_multi_source.py → crawl/monitor.py (crawl per source)
consulting/cli.py (🔴) → consulting_readiness.py, freshness_gate.py,
                         coverage_truth.py, opportunity_intel/*, contract_intel/*
```

### Bibliotecas Compartilhadas

| Módulo | Usado por |
|--------|----------|
| `scripts/lib/universe.py` | `coverage_truth.py`, `consulting_readiness.py` |
| `scripts/crawl/registry.py` | `backfill_multi_source.py`, `coverage_truth.py` |
| `config/settings.py` | `collect-metrics.py`, `check-alerts.py` |
| `config/logging_config.py` | `collect-metrics.py`, `check-alerts.py`, `notify.py` |
| `scripts/lib/` (helpers) | Múltiplos scripts |

### Infraestrutura Externa

- **PostgreSQL**: Acessado via `psycopg2` com DSN de `LOCAL_DATALAKE_DSN` (default: `postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres`)
- **Redis** (opcional): Cache via `redis_pool.py`
- **Supabase** (opcional): Acesso via `supabase_client.py`
- **SMTP/Webhook**: Notificações via `notify.py`
- **Storage Box**: Backup externo verificado em `check-alerts.py`

## Decisões de Design

| Decisão | Opção Rejeitada | Justificativa |
|---------|----------------|---------------|
| Scripts autônomos com argparse vs framework CLI unificado | Click/Typer/CLI framework | Simplicidade e independência — cada script pode rodar standalone; sem dependência adicional |
| Subprocess vs in-process para pipeline intel | In-process (evitar overhead) | Isolamento: cada estágio pode falhar sem derrubar o orquestrador; timeouts independentes |
| Registry central de fontes vs lista hardcoded | Lista em cada script | Fonte única de verdade; coverage_truth.py e backfill_multi_source.py usam `registry.iter_sources()` |
| systemd timers vs cron | Cron (mais simples) | systemd oferece logging, environment, dependencies, OnFailure integrados |
| DSN via env var vs config file | Config YAML/TOML | Simplicidade 12-factor; mas default hardcoded reduz portabilidade |
| Dois scripts de health check vs um | Manter apenas health-dashboard.py | 🔴 Duplicação identificada: `health_check.py` e `healthcheck.py` têm sobreposição |

## Riscos e Lacunas

### 🔴 LACUNAS (severidade alta)

| ID | Lacuna | Impacto | Recomendação |
|----|--------|---------|--------------|
| L-RS01 | `scripts/consulting/cli.py build-delivery` não existe | EPIC P1-03 bloqueado; não é possível gerar entrega unificada | Implementar comando com 8 etapas (plano-mestre §16) |
| L-RS02 | Nomenclatura kebab-case e snake_case coexistem | Confusão em imports e manutenção: `intel-collect.py` vs `intel_collect.py`, `collect-report-data.py` vs `collect_report_data.py` | Padronizar para snake_case; criar aliases ou deprecar kebab |
| L-RS03 | Três scripts de health check (`health_check.py`, `healthcheck.py`, `health-dashboard.py`) com funcionalidade sobreposta | Manutenção duplicada, comportamentos inconsistentes | Unificar em `health-dashboard.py` e deprecar os outros |
| L-RS04 | Radar de oportunidades (QW-01) não reconcilia snapshot — 639 registros órfãos vs 34 confirmados | Falsos positivos no radar | Implementar reconciliação de snapshot PNCP (plano-mestre §2.2) |

### 🟡 RISCOS (severidade média)

| ID | Risco | Probabilidade | Mitigação |
|----|-------|--------------|-----------|
| R-RS01 | DSN hardcoded em múltiplos scripts — mudança de conexão exige alterar N arquivos | Média | Centralizar em `config/settings.py` e forçar leitura de lá |
| R-RS02 | Subprocess pipeline intel sem health check de estágio — se filho trava, orquestrador espera timeout | Média | Implementar heartbeat ou check periódico |
| R-RS03 | Scripts sem testes unitários individuais (apenas testes integrados de pipeline) | Alta | Adicionar testes unitários para cada entry point |
| R-RS04 | `consulting_readiness.py` mantém carregador de universo duplicado (plano-mestre §2.1) | Média | Remover e usar exclusivamente `scripts/lib/universe.py` |

### 🟢 CONFIRMADO

- **21 scripts CLI** com `if __name__ == '__main__'` verificados via AST
- **20+ systemd timers** com schedules documentados em `deploy/systemd/`
- **5 quality gates** inline em `intel_pipeline.py` com auto-fix
- **3 níveis de saída** padronizados: 0=ok, 1=warning, 2=critical
- **Freshness gate** com SLA configurável para fontes críticas
- **Source blockers** documentados em `coverage_truth.py` (7 fontes bloqueadas)
