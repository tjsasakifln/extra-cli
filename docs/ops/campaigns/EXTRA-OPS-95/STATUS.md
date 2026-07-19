# EXTRA-OPS-95-FOUNDATION — Status operacional

**Atualizado:** 2026-07-19T07:46Z  
**Status global:** **PARTIAL**

## Métricas honestas (pós-purge de identidade falsa)

| Métrica | Valor | Meta |
|---------|------:|-----:|
| Ops proxy contratos (presença∪SZ) | **991/1093 (90.6679%)** | 1039 (95%) — gap **48** |
| Presença contratos | **368 (33.6688%)** | — |
| success_zero contratos | **623** | — |
| Presença editais | **279 (25.5261%)** | 1039 (95%) |
| CNPJ-14 cache (só raiz válida) | **705** | — |
| DOD | ~15,7% | ≥55% |

## Correção adversarial (2026-07-19)

`token_containment` / `name_exact` sem checagem de raiz CNPJ-8 geravam CNPJ-14 de **outro órgão**.

- 48 entradas de cache inválidas purgadas
- 39 success_zero falsos deletados
- Ops proxy **94,2% → 90,7%** (honesto)
- `pick_match` agora **exige cnpj14[:8]==cnpj8** em todos os caminhos
- Evidência: `evidence/M2-cnpj14/purge-token-mismatch.json`

## Claims proibidos

95% cobertura · 7 estágios · pré-purge 94% · campanha DONE · DOD 55% · either
