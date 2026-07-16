# L1.5 — Golden path no HEAD

**Story:** PE-L1-03  
**Data:** 2026-07-16  
**HEAD base:** `1f7aa7c` (+ campanha `epic/plano-executivo-30d`)

## Execução

| Campo | Valor |
|-------|--------|
| Comando | `python3 scripts/golden_path.py --skip-freshness --skip-reports` |
| Run ID | `gp-20260716-191038` |
| DB | `127.0.0.1:5433/pncp_datalake` — connectivity **pass** (46 ms) |
| Wall clock | ~34.7 s |
| Exit code processo | **1** (ledger crash pós-pipeline) |
| Pipeline (antes do crash) | `success` (fontes essenciais OK) |

## Fontes

| Fonte | Status | Detalhe |
|-------|--------|---------|
| pncp | fail | timeout after 15s (não essencial neste run) |
| pcp | success | fetched 181, inserted 46 |
| compras_gov | success | fetched 2, inserted 2 |

## Artefatos

- `output/golden-path/evidence-gp-20260716-191038.json`
- `output/golden-path/crawl-pcp-gp-20260716-191038.json`
- `output/golden-path/crawl-compras_gov-gp-20260716-191038.json`

## Bug encontrado e correção

- **Causa:** `_save_final_ledger` passava o dict do ledger inteiro para `_save_ledger`, que esperava `list`, corrompendo `ledger.json` com `runs` aninhado → `AttributeError: 'dict' object has no attribute 'append'`.
- **Correção:** `scripts/golden_path.py` — normalização de runs + append na lista plana (PE-L1-03).
- **Estado:** código corrigido na campanha; reexecução completa com reports fica follow-up.

## Veredito L1.5

**PARTIAL** — golden path de fontes essenciais (PCP + ComprasGov) OK no HEAD; PNCP timeout; reports/freshness skipped; ledger bug corrigido após evidência.
