# EXTRA-OPS-95 — Status operacional (em andamento)

**HEAD start:** `dbc5adb2ab62898cd3fd005c83c90dcef36c1cde`  
**Atualizado:** 2026-07-19T02:08Z (UTC)  
**Branch canônica de partida:** `main`

## Objetivo vinculante

Operação local consultiva B2G com cobertura **editais ≥95%** e **contratos ≥95%** **separadas**, ciclo decisão→ação, packages, 3 ciclos correlacionáveis, recall independente, HTML/DOD honestos.

## Progresso por fase

| Fase | Status | Evidência |
|------|--------|-----------|
| M0 Recuperação | **DONE** | `RECOVERY-INVENTORY.md`, baseline live |
| M1 Contrato/baseline | **DONE** | `baseline/metrics-live.json`, `plans/PLAN-30D.md`, ROI DECISION-001 |
| M2 Cobertura | **IN_PROGRESS** | promote ops 0→**407/1093 (37,24%)**; presença editais 26% / contratos 34% |
| M3 Intel/decisão | **PARTIAL** | workspace today OK; GO demoted 1549→0 (perfil incompleto); radar upsert fix |
| M4 Concorrentes/valores | **PENDING** | componentes herdados; não re-provados nesta sessão |
| M5 Automação/3 ciclos | **PENDING** | contracts 30d crawl em background |
| M6 Recall | **BLOCKED_SOURCE** | herdado N09 |
| M7 HTML/DOD/handoff | **PENDING** | sem selo falso |

## Métricas live (não confundir)

| Métrica | Antes (R2 N06c) | Agora | Meta |
|---------|----------------:|------:|-----:|
| Denominador | 1093 | **1093** | fixo |
| Presença editais | 285 (26,08%) | **285 (26,08%)** | ≥1039 (95%) |
| Presença contratos | 368 (33,67%) | **368 (33,67%)** | ≥1039 (95%) |
| Either (proibido) | 406 (37,15%) | **406 (37,15%)** | n/a |
| Strict operational (registry) | ~0–8% | **407 (37,24%)** | ≥1039 (95%) |
| GO abertos com perfil incompleto | 1549 | **0** | 0 |
| Contratos rows | 1.082.055 | 1.082.055 | — |
| Bids rows | 10.974 | 10.974 | — |

### Interpretação honesta

- **Ganho material:** promoção de evidência real (PG + crawl artifacts + contracts-only) elevou cobertura **operacional strict** de ~0–8% para **37,24%**.
- **Presença** de editais/contratos **não subiu** nesta onda — o ganho foi de **estágios + proveniência**, não de novos órgãos.
- Meta 60% strict: faltam **~249** entidades; 80%: **~468**; 95%: **~632**.
- Either **não** é progresso de cobertura.

## Decisões ROI

1. **DECISION-001:** override do rank-next (checkbox claims) → **COV-EDIT-CONTRACT-OPS**.
2. N01 **DONE** — não reabrir; `resume.md` R2 stale.
3. PR #28 CONFLICTING — **não mergear**; extrair deltas só se úteis.
4. SmartLic **DEFERRED_STALE**.
5. GO sem perfil de capacidade → **REVIEW** (código + demote em massa).

## Código alterado nesta campanha (ainda local)

- `scripts/opportunity_intel/ranking.py` — demote GO se perfil incompleto
- `scripts/opportunity_intel/pncp_audit.py` — upsert `coverage_evidence` sem duplicate key
- `tests/test_opportunity_ranking.py` — cobre demote + GO score-path

## O que Tiago já pode usar

- Workspace `today` com filas REVIEW, prazos, perfil pendente
- Lista de oportunidades **sem GO indevido** enquanto perfil de capacidade estiver incompleto
- Métricas de cobertura separadas (presença) e strict operational no registry
- Pacotes/crawlers herdados (PNCP, contracts, multi-source)

## O que ainda **não** deve usar como “95% pronto”

- Cobertura 95% editais ou contratos
- Recall estratificado
- GO automático calibrado
- VPS / LOCAL_READY
- Dataset SmartLic

## Próximos passos ordenados (ROI)

1. Expandir janela de contratos (365d→3y) com checkpoint — aumenta órgãos únicos
2. CIGA DOM + sc_compras residual com promote full provenance
3. success_zero nominal por entidade aplicável PNCP (com run/raw/hash)
4. Três ciclos full correlacionáveis (run_id)
5. Dossiers + package daily/weekly reconciliados
6. Gold sample recall (ou BLOCKED honesto)
7. HTML executivo + DOD states

## Claims proibidos agora

- “95% cobertura”
- “either = cobertura”
- “LOCAL_READY / PROJECT_DONE”
- “recall 95%”
- “GO confiável com perfil incompleto”
