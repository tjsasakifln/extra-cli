# EXTRA-OPS-95-FOUNDATION — Status operacional

**HEAD start (main):** `dbc5adb2ab62898cd3fd005c83c90dcef36c1cde`  
**Atualizado:** 2026-07-19T03:34Z (UTC)  
**HEAD trabalho:** `1c2f608`+  
**Status global da campanha:** **PARTIAL**

## Objetivo vinculante

Operação local consultiva B2G com cobertura editais/contratos ≥95% **separadas**, ciclo GO/REVIEW/NO_GO, packages, 3 ciclos, recall independente, DOD ≥55% com evidência, HTML honesto, OSS só com benchmark.

## Progresso por fase

| Fase | Status | Evidência |
|------|--------|-----------|
| M0 Recuperação + baseline | **DONE** | `baseline/foundation-baseline.json`, `BASELINE.md`, `RECOVERY-INVENTORY.md` |
| M0.5 OSS harvest | **DONE** (decisões) | `oss/oss-decisions.json` — 0 ADOPT sem piloto |
| M1 Universo | **DONE** parcial operacional | Seed 1093; radar universe_resolution **100%**; 2ª import 0 inserts |
| M2 Cobertura | **IN_PROGRESS** | Presença editais **279 (25,5%)** / contratos **247 (22,6%)**; multi-source sc_compras+ciga; enrich CNPJ |
| M3 Intel/decisão | **PARTIAL** | **401** opps; GO=0 REVIEW=397 NO_GO=4; upsert fix 057 |
| M4 Concorrentes/valores | **PARTIAL** | packages live: competitors/expiring/prices/opps + package-final fixture |
| M5 Automação/3 ciclos | **PENDING** | — |
| M6 Recall | **BLOCKED_SOURCE** | N09 |
| M7 HTML/DOD/handoff | **PARTIAL** | handoff sessão; HTML final não |
| B1 OCDS | **PARTIAL** | thin mapping + tests + live sample 0 issues |
| B2 Data contracts | **PARTIAL** | Pydantic 7 tests; Pandera DEFER |

## Métricas live (rebuild + re-coleta)

| Métrica | Valor | Meta |
|---------|------:|-----:|
| DOD checked | **213/1355 (15,72%)** | ≥746 (55%) |
| Denominador 200 km | **1093** | fixo |
| Universe resolution | **100%** | 100% |
| Bids rows | **10831** (pncp+sc_compras) | — |
| Contracts rows | **217115+** (persist por janela; 6+ janelas) | — |
| Presença editais | **279 (25,53%)** | ≥1039 operacional |
| Presença contratos | **293 (26,81%)** | ≥1039 operacional |
| Registry operational | **139 (12,72%)** | ≥1039 |
| Oportunidades | **401** (0 GO / 397 REVIEW / 4 NO_GO) | fluxo útil |
| M4 packages | competitors/expiring/prices + PDF+Excel fixture | contratado≠pago |
| success_zero bulk | **NOT_READY** | CNPJ-14: 80/80 batch OK; SZ pagination path pending |
| CNPJ-14 residual batch | **80/80** resolvidos (cnpj8_prefix) | cache `data/cnpj14_cache/` |

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
- `scripts/ops/enrich_sc_compras_cnpj.py` — match nome→CNPJ em sc_compras
- (herdado) GO demote ranking

## Próximos passos

1. Resolver CNPJ-14 dos ~800 entes residual (OpenCNPJ/Receita) para success_zero
2. Contratos com janelas menores + checkpoint (evitar 30d nacional monólito)
3. Multi-source residual (CIGA/sc_compras)
4. Promote strict operational com proveniência completa
5. Packages daily/weekly + 3 ciclos
6. Gold sample N09 ou BLOCKED honesto
7. HTML + DOD reconciliados sem inflação

## Claims proibidos

95% cobertura · either · LOCAL_READY · recall 95% · DOD 55% · campanha DONE · SmartLic operacional
