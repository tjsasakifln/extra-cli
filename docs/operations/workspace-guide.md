# Workspace Guide — Tiago (Extra Construtora)

Guia operacional do dia a dia.  
**Atualizado:** 2026-07-25 · Facade ADR-017 · Host de record: Netcup (`ssh ec-prod`)  
**Onboarding:** [`README.md`](../../README.md) · **Dev canônico:** [`docs/DEVELOPMENT.md`](../DEVELOPMENT.md)

Ciclo semanal (não substituir por scripts ad hoc):

```bash
make extra-weekly
# python3 -m scripts.ops.weekly_cycle --strict
```

## Rotina diária (~15 min)

```bash
cd "/path/to/extra-consultoria"
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"

# 1) Fila do dia (oportunidades, prazos, perfil pendente, fontes)
python3 -m scripts.workspace today

# 2) Contrato de cobertura (NÃO confundir sinal comercial com cobertura)
python3 -m scripts.coverage.coverage_contract_cli report --format table
python3 -m scripts.coverage.coverage_contract_cli report -o output/coverage/contract-report.json
python3 -m scripts.workspace coverage

# 3) Source registry / gaps nominais
python3 -m scripts.source_registry stats
python3 -m scripts.source_registry gaps --output output/coverage/
python3 -m scripts.source_registry sync-db --dsn "$LOCAL_DATALAKE_DSN"

# 4) Triagem de oportunidades
python3 -m scripts.workspace opportunities --ranking GO,REVIEW --limit 30
python3 -m scripts.workspace dossier <ID>

# 5) Atualizar PNCP se freshness baixa
python3 -m scripts.opportunity_intel.cli update --source pncp
# ou multi-fonte:
python3 -m scripts.crawl.monitor --source pncp --mode incremental

# 6) Briefing comercial
python3 -m scripts.workspace briefing

# 7) Registrar decisão humana
python3 -m scripts.workspace decide --id <ID> --decision approve --reason "Fit reforma + prazo + valor"
```

## Comandos por capacidade

| Capacidade | Comando |
|------------|---------|
| Fila diária | `python3 -m scripts.workspace today` |
| Oportunidades | `python3 -m scripts.workspace opportunities --status open --limit 50` |
| Dossiê | `python3 -m scripts.workspace dossier <id>` |
| Cobertura multi-métrica | `python3 -m scripts.workspace coverage` |
| Concorrentes | `python3 -m scripts.workspace competitors` |
| Contratos vincendos | `python3 -m scripts.workspace expiring-contracts` |
| Preços (estimado) | `python3 -m scripts.workspace prices --keywords reforma` |
| Análise de edital | `python3 -m scripts.workspace edital analyze caminho/edital.pdf` |
| Apoio a proposta | `python3 -m scripts.workspace proposal support <id>` |
| Decisão HITL | `python3 -m scripts.workspace decide --id N --decision approve\|reject\|override --reason "..."` |
| Registry build | `python3 -m scripts.source_registry build` |
| Discovery | `python3 -m scripts.source_registry discover --limit 50 --dry-run` |
| Aquisição PNCP | `python3 -m scripts.source_registry acquire --strategy pncp_orgao_probe --limit 100` |
| Aquisição CIGA | `python3 -m scripts.source_registry acquire --strategy ciga_municipio_expand` |
| Recall preliminar | `python3 -m scripts.coverage.recall_benchmark evaluate --sample docs/qa/recall-sample-2026-07-17.json` |
| DOE-SC público | `python3 -m scripts.crawl.doe_sc_publications --year 2025 --sla-hours 24` |
| DOM-SC público | `python3 -m scripts.crawl.ciga_dom_publications --mode incremental --max-zips 15` |

## Métricas (ler com atenção)

| Métrica | O que é | Meta |
|---------|---------|------|
| `entities_with_recent_commercial_signal` | Entes com ≥1 OPEN/UPCOMING/RECENT | **Não é cobertura** |
| `source_mapping_coverage` | Registro explícito de fontes | **100%** |
| `operational_source_coverage` | Sete estágios, proveniência completa e sucesso dentro do SLA | **≥95%** |
| `freshness_coverage` | Verificado dentro do SLA | **≥95%** |
| `opportunity_recall` | Amostra estratificada de portais | **≥95%** (não claimar sem amostra-ouro atual) |
| `required_field_completeness` | Campos de decisão preenchidos | alto |
| Dual `historical_contracts` | Spine ADR-030 | Meta ≥95%; ver campanha HC / non-claims no README |

Recomendações GO/REVIEW são o melhor entre o que o sistema encontrou com dados disponíveis — **não** garantem recall do universo real.

## Perfil Extra (elicitação pendente)

Edite `config/client_profiles/extra.yaml`:

- `capacity.*` (obras simultâneas, capital de giro, garantias)
- `qualifications.cats_atestados`
- `commercial_preferences.minimum_margin_pct`
- `known_competitors`, `priority_organs`

Campos `PENDING_ELICITATION` **não são inventados**.

## Fora de escopo

Acompanhamento físico de obra (medição, diário de obra, fiscalização presencial).
