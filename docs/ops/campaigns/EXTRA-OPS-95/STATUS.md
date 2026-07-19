# EXTRA-OPS-95-FOUNDATION — Status operacional

**HEAD start (main):** `dbc5adb2ab62898cd3fd005c83c90dcef36c1cde`  
**Atualizado:** 2026-07-19T06:55Z (UTC)  
**HEAD trabalho:** ver `git log -1`  
**Status global da campanha:** **PARTIAL**

## Objetivo vinculante

Operação local consultiva B2G com cobertura editais/contratos ≥95% **separadas**, ciclo GO/REVIEW/NO_GO, packages, 3 ciclos, recall independente, DOD ≥55% com evidência, HTML honesto, OSS só com benchmark.

## Progresso por fase

| Fase | Status | Evidência |
|------|--------|-----------|
| M0 Recuperação + baseline | **DONE** | `baseline/foundation-baseline.json` |
| M0.5 OSS harvest | **DONE** (decisões) | `oss/oss-decisions.json` |
| M1 Universo | **DONE** parcial | Seed 1093; universe_resolution **100%** |
| M2 Cobertura | **IN_PROGRESS** | Contratos ops proxy **85,1%**; editais presença **25,5%** |
| M3 Intel/decisão | **PARTIAL** | 401 opps; GO=0 REVIEW≈397 |
| M4 Packages | **PARTIAL** | live + fixture |
| M5 Automação | **PARTIAL** | 3 ciclos + backup/resume |
| M6 Recall | **BLOCKED_SOURCE** | N09 |
| M7 HTML/DOD/handoff | **PARTIAL** | — |

## Métricas live (2026-07-19T06:55Z)

| Métrica | Valor | Meta |
|---------|------:|-----:|
| DOD checked | **~213/1355 (15,7%)** | ≥746 (55%) |
| Denominador 200 km | **1093** | fixo |
| Presença editais | **279 (25,53%)** | ≥1039 |
| Presença contratos | **340 (31,11%)** | ≥1039 |
| success_zero contratos | **590** entidades | — |
| **Ops proxy contratos** (presença∪SZ) | **930 (85,09%)** | proxy ≠ 7 estágios; meta 95% = 1039 (**gap 109**) |
| CNPJ-14 cache | **644** únicos | residual hard ~100 not on matriz 0001 |
| Bids / contracts rows | 10831 / 217359 | — |
| Oportunidades | 401 | — |

Fonte: `evidence/session-metrics.json`

## Breakthrough desta sessão

1. **`resolve_cnpj14_matriz`**: CNPJ-14 = `cnpj8 + 0001 + DV` verificado em `GET /api/pncp/v1/orgaos/{cnpj}` → **+457** resoluções (187→644)
2. Waves SZ entity-scoped com `http_204_complete` → **22 → 590** entidades success_zero
3. Ops proxy contratos: **~29% → 85%**
4. Branch `0002` testada: 0 hits nos 80 residual (não é atalho geral)
5. Testes unitários: `tests/unit/ops/test_resolve_cnpj14_matriz.py` (4 passed)

## Claims proibidos (permanecem)

- 95% cobertura operacional (ainda gap 109 no proxy e editais em 25%)
- ops_proxy como cobertura de 7 estágios
- campanha DONE / DOD 55% / LOCAL_READY
- either / união como meta

## Próximos passos

1. Residual ~109: OpenCNPJ/Receita por razão social, ou fontes multi-org (TCE/sc_compras) para presença
2. **Editais** (279): crawls multi-source + matching; API publicacao+cnpjOrgao não confiável
3. Fechar HAS_DATA residual + national contracts crawl controlado
4. N09 gold sample ou BLOCKED_SOURCE formal
5. DOD flips só com evidência; HTML executivo
