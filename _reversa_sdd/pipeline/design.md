# Pipeline — Design Técnico (v1.0)

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d

## Interface

| Símbolo | Assinatura | Retorno | Observação |
|---------|-----------|---------|------------|
| `backfill_multi_source` | `(sources, mode, conn)` | `BackfillResult` | Coordena múltiplos crawlers |
| `run_intel_pipeline` | `(cnpj, ufs, conn)` | `PipelineResult` | Crawl+match+enrich+score |

## Fluxo Principal (Backfill)

1. Load source registry → enumerar fontes ativas
2. Para cada fonte: crawl → transform → persist → reconcile
3. Checkpoints por fonte permitem retomada
4. Evidence ledger atualizado após cada fonte

## Fluxo Principal (Intel Pipeline)

1. `intel_pipeline.py --cnpj <CNPJ> --ufs SC`
2. Crawl fontes configuradas para a UF
3. Entity matching (órgão → sc_public_entities)
4. Enriquecimento (IBGE, distância)
5. Scoring + ranking
6. Output: relatório consolidado

## Dependências

- `scripts/crawl/` — todos os crawlers
- `scripts/matching/` — entity matching
- `scripts/lib/` — universe, geocode
- `scripts/opportunity_intel/` — scoring, ranking, status

## Riscos e Lacunas

- 🔴 Orquestração local sem Makefile ou docker-compose
- 🟡 68K LOC combinados em 2 arquivos — densidade alta
- 🟡 Backfill sem transação global: falha em fonte N não rollback fontes 1..N-1
