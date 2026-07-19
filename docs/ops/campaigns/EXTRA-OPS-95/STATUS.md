# EXTRA-OPS-95-FOUNDATION — Status operacional

**HEAD start (main):** `dbc5adb2ab62898cd3fd005c83c90dcef36c1cde`  
**Atualizado:** 2026-07-19T03:20Z (UTC)  
**Status global da campanha:** **PARTIAL**

## Objetivo vinculante

Operação local consultiva B2G com cobertura editais/contratos ≥95% **separadas**, ciclo GO/REVIEW/NO_GO, packages, 3 ciclos, recall independente, DOD ≥55% com evidência, HTML honesto, OSS só com benchmark.

## Progresso por fase

| Fase | Status | Evidência |
|------|--------|-----------|
| M0 Recuperação + baseline | **DONE** | `baseline/foundation-baseline.json`, `BASELINE.md`, `RECOVERY-INVENTORY.md` |
| M0.5 OSS harvest | **DONE** (decisões) | `oss/oss-decisions.json` — 0 ADOPT sem piloto |
| M1 Universo | **DONE** parcial operacional | Seed 1093; radar universe_resolution **100%**; 2ª import 0 inserts |
| M2 Cobertura | **IN_PROGRESS** | Presença editais 24,5% / contratos 22,6%; strict ops registry 12,7% |
| M3 Intel/decisão | **PARTIAL** | **401** opps; GO=0 REVIEW=397 NO_GO=4; upsert fix 057 |
| M4 Concorrentes/valores | **NOT_READY** | contract_intel parcial (expiring) |
| M5 Automação/3 ciclos | **PENDING** | — |
| M6 Recall | **BLOCKED_SOURCE** | N09 |
| M7 HTML/DOD/handoff | **PARTIAL** | handoff sessão; HTML final não |
| B1 OCDS | **PARTIAL** | thin mapping + tests + live sample 0 issues |
| B2 Data contracts | **PARTIAL** | Pydantic 7 tests; Pandera DEFER |

## Métricas live (rebuild + re-coleta)

| Métrica | Valor | Meta |
|---------|------:|-----:|
| DOD checked | **195/1355 (14,39%)** | ≥746 (55%) |
| Denominador 200 km | **1093** | fixo |
| Universe resolution | **100%** | 100% |
| Bids rows | **8221** | — |
| Contracts rows | **72925** (+90d crawl se em curso) | — |
| Presença editais | **268 (24,52%)** | ≥1039 operacional |
| Presença contratos | **247 (22,60%)** | ≥1039 operacional |
| Registry operational | **139 (12,72%)** | ≥1039 |
| Oportunidades | **401** (0 GO / 397 REVIEW / 4 NO_GO) | fluxo útil |

## Decisões

1. ROI override **COV-EDIT-CONTRACT-OPS** (DECISION-001)
2. N01 DONE — não reabrir
3. PR #28 — não mergear
4. SmartLic dataset DEFER/REJECT path crítico
5. Pandera DEFER; Pydantic ADAPT baseline
6. OCDS ADAPT thin; Kingfisher REJECT full
7. GO sem perfil Extra → REVIEW (score cap 69)

## Fixes de código desta sessão

- `scripts/opportunity_intel/cli.py` — loop modalidades 1–19
- `db/migrations/057_*` + 027 — upsert content_hash + array JSON seguro
- `db/migrations/018_*` — cast esfera_id TEXT em fresh install
- `scripts/data_contracts/*` — contratos fail-closed
- `scripts/ocds_bridge/*` — mapping OCDS thin
- (herdado) GO demote ranking

## Próximos passos

1. Concluir/retomar contracts 90d→365d com checkpoint
2. success_zero nominal por ente aplicável
3. Multi-source residual (CIGA/sc_compras)
4. Promote strict operational com proveniência completa
5. Packages daily/weekly + 3 ciclos
6. Gold sample N09 ou BLOCKED honesto
7. HTML + DOD reconciliados sem inflação

## Claims proibidos

95% cobertura · either · LOCAL_READY · recall 95% · DOD 55% · campanha DONE · SmartLic operacional
