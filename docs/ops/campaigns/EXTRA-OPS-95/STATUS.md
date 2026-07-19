# EXTRA-OPS-95-FOUNDATION — Status operacional

**HEAD start (main):** `dbc5adb2ab62898cd3fd005c83c90dcef36c1cde`  
**Atualizado:** 2026-07-19T04:51Z (UTC)  
**HEAD trabalho:** `d16f70e`+ (working tree dirty — commit pending)  
**Status global da campanha:** **PARTIAL**

## Objetivo vinculante

Operação local consultiva B2G com cobertura editais/contratos ≥95% **separadas**, ciclo GO/REVIEW/NO_GO, packages, 3 ciclos, recall independente, DOD ≥55% com evidência, HTML honesto, OSS só com benchmark.

## Progresso por fase

| Fase | Status | Evidência |
|------|--------|-----------|
| M0 Recuperação + baseline | **DONE** | `baseline/foundation-baseline.json`, `BASELINE.md`, `RECOVERY-INVENTORY.md` |
| M0.5 OSS harvest | **DONE** (decisões) | `oss/oss-decisions.json` — 0 ADOPT sem piloto |
| M1 Universo | **DONE** parcial operacional | Seed 1093; radar universe_resolution **100%** |
| M2 Cobertura | **IN_PROGRESS** | Editais presença **279 (25,5%)**; contratos presença **300 (27,4%)**; ops proxy presença∪SZ **422 (38,6%)** |
| M3 Intel/decisão | **PARTIAL** | **401** opps; GO=0 REVIEW≈397 NO_GO=4 |
| M4 Concorrentes/valores | **PARTIAL** | packages live + fixture PDF/Excel |
| M5 Automação/3 ciclos | **PARTIAL** | 3 ciclos controlados + backup/resume proof |
| M6 Recall | **BLOCKED_SOURCE** | N09 sem amostra-ouro independente |
| M7 HTML/DOD/handoff | **PARTIAL** | handoff sessão; HTML final não |
| B1 OCDS | **PARTIAL** | thin mapping + tests |
| B2 Data contracts | **PARTIAL** | Pydantic; Pandera DEFER |

## Métricas live (2026-07-19T04:51Z)

| Métrica | Valor | Meta |
|---------|------:|-----:|
| DOD checked | **213/1355 (15,72%)** | ≥746 (55%) |
| Denominador 200 km | **1093** | fixo |
| Universe resolution | **100%** | 100% |
| Bids rows | **10831** | — |
| Contracts rows | **217184** | — |
| Presença editais (cnpj8) | **279 (25,53%)** | ≥1039 operacional |
| Presença contratos (cnpj8) | **300 (27,45%)** | ≥1039 operacional |
| success_zero contracts ents | **122** | — |
| Ops proxy contratos (presença∪SZ) | **422 (38,61%)** | proxy — **não** = 7 estágios |
| CNPJ-14 cache único | **187** | residual need ≈558 |
| Oportunidades | **401** (0 GO / ~397 REVIEW / 4 NO_GO) | fluxo útil |

Fonte: `evidence/session-metrics.json`

## Avanço M2 nesta continuação

1. **CLI estável success_zero:** `scripts/ops/probe_entity_success_zero.py` (HTTP 204/empty + backoff 429)
2. **CLI estável CNPJ-14:** `scripts/ops/resolve_cnpj14_batch.py`
3. **SZ batch3:** +93 success_zero escritos (total 122 entidades)
4. **HAS_DATA:** 7 entidades com dados → upsert via transform oficial → presença 293→**300**
5. Cache CNPJ deduplicado (havia 95 dups de writers concorrentes)
6. Rate limit PNCP (429) mitigado serializando resolve vs SZ vs crawl nacional

## Decisões

1. ROI override **COV-EDIT-CONTRACT-OPS** (DECISION-001)
2. N01 DONE — não reabrir
3. PR #28 — não mergear
4. SmartLic dataset DEFER/REJECT path crítico
5. Pandera DEFER; Pydantic ADAPT baseline
6. OCDS ADAPT thin; Kingfisher REJECT full
7. GO sem perfil Extra → REVIEW (score cap 69)
8. Ops proxy ≠ cobertura operacional de 7 estágios (claim proibida)
9. Editais entity-scoped via `cnpjOrgao` na API publicacao: **não confiável** (400 / filtro incerto) — não gravar SZ de editais sem prova

## Próximos passos

1. Continuar resolve CNPJ-14 residual (~558) com delay ≥1s
2. Rodar SZ em wave após cada lote de CNPJ novos
3. Crawl nacional contratos com checkpoint (1 processo; respeitar 429)
4. Multi-source residual (CIGA/DOM) para editais
5. Gold sample N09 ou BLOCKED_SOURCE honesto
6. Packages daily/weekly + 3 ciclos calendário
7. HTML + DOD reconciliados sem inflação

## Claims proibidos

95% cobertura · either · LOCAL_READY · recall 95% · DOD 55% · campanha DONE · SmartLic operacional · ops_proxy como cobertura 7-estágios
