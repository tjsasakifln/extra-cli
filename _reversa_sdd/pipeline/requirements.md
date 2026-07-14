# Pipeline — Requirements (v1.0)

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d

## Visão Geral

Pipeline de backfill multi-fonte e orquestração de ingestão. Conecta crawlers → transform → persist para múltiplas fontes em uma execução coordenada.

## Responsabilidades

- Backfill multi-fonte: execução coordenada de crawlers
- Pipeline de inteligência: crawl + match + enrich + score para um CNPJ
- Orquestração de fluxo completo: crawl → transform → persist → reconcile

## Requisitos Funcionais

| ID | Requisito | Prioridade | Fonte |
|----|-----------|-----------|-------|
| RF-PP01 | `backfill_multi_source.py` — backfill coordenado de múltiplas fontes | Must | `scripts/pipeline/backfill_multi_source.py` |
| RF-PP02 | `intel_pipeline.py` — pipeline completa para 1 CNPJ | Must | `scripts/intel_pipeline.py` |

## Regras de Negócio

- **Regra PP-01:** Backfill coordena mas não substitui crawlers individuais. Cada fonte mantém seu próprio checkpoint. 🟡
- **Regra PP-02:** Pipeline de inteligência opera por CNPJ, com UF como escopo geográfico. 🟢 `intel_pipeline.py`

🔴 **LACUNA:** Orquestração local reproduzível (EPIC P1-04) não implementada. Falta Makefile, docker-compose.local.yml.

## Tarefas

| # | Tarefa | Confiança |
|---|--------|-----------|
| T-PP01 | Documentar `backfill_multi_source.py` (~34K LOC) | 🟡 |
| T-PP02 | Documentar `intel_pipeline.py` (~34K LOC) | 🟡 |
| T-PP03 | 🔴 Implementar Makefile + docker-compose.local.yml (P1-04) | 🔴 |
| T-PP04 | Criar `scripts/run_local_pipeline.sh` reproduzível | 🔴 |
