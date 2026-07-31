# Final report — CONFENGE-PUBLIC-AGENCY-TECHNICAL-SERVICES-01

**Status:** `READY_FOR_TIAGO_REVIEW_PUBLIC_AGENCY_VERTICAL`  
**PR:** https://github.com/tjsasakifln/extra-cli/pull/185  
**Run SHA (dual launch = tip):** `b2a87b252924b42ef1118ba567ef08987ddc42a2`  
**Updated (UTC):** 2026-07-31T00:42:56Z

## Freeze isolation (CI)

Supplier commercial-ready freeze surface restored:
- `scripts/ops/confenge_commercial_cycle.py` byte-identical to freeze `d469b87`
- Makefile CONFENGE commercial-ready + final-evidence section hashes unchanged
- Multi-target `TARGET=suppliers|public-agencies|all` via `scripts/ops/confenge_commercial_target_router.py` + post-freeze Makefile redefine

## Eng-match (occupancy absolute + obra de arte)

Multi-tier `classify_engineering_object` with occupancy always winning; cultural OBRA DE ARTE hard-neg.

## Dual launch SC

| Metric | Value |
|--------|-------|
| evaluated | 276 |
| publishable / top_n | **9** (honest, no pad) |
| no_weak_false_eng | true |
| dual equal | true |
| code_sha | `b2a87b252924b42ef1118ba567ef08987ddc42a2` |

## Top 9

| # | Órgão | Pop | #STRONG_WORKS | reasons | Mode | Oferta |
|---|-------|-----|---------------|---------|------|--------|
| 1 | MUNICÍPIO DE ITAIÓPOLIS | 22051 | 1 | ['obra_de', 'execucao_obra', 'pavimentacao', 'drenagem_works', 'drenagem_works_context', 'keyword:OBRA', 'keyword:PAVIMENTACAO', 'keyword:DRENAGEM'] | PROACTIVE_INSTITUTIONAL_PROSPECT | — |
| 2 | MUNICÍPIO DE POUSO REDONDO | 17123 | 1 | ['construcao_de', 'keyword:CONSTRUCAO'] | PROACTIVE_INSTITUTIONAL_PROSPECT | — |
| 3 | MUNICÍPIO DE GAROPABA | 29959 | 1 | ['obra_de', 'execucao_obra', 'pavimentacao', 'keyword:OBRA', 'keyword:PAVIMENTACAO'] | PROACTIVE_INSTITUTIONAL_PROSPECT | — |
| 4 | Prefeitura Municipal de Catanduvas | 10566 | 1 | ['projeto_estrutural', 'memorial_descritivo', 'keyword:OBRA', 'keyword:MEMORIAL DESCRITIVO'] | PROACTIVE_INSTITUTIONAL_PROSPECT | — |
| 5 | MUNICÍPIO DE CAMPOS NOVOS | 36932 | 1 | ['obra_de', 'execucao_obra', 'construcao_de', 'projeto_basico', 'keyword:OBRA', 'keyword:CONSTRUCAO', 'keyword:PROJETO BASICO'] | PROACTIVE_INSTITUTIONAL_PROSPECT | — |
| 6 | MUNICÍPIO DE ÁGUAS DE CHAPECÓ | 6036 | 1 | ['obra_de', 'execucao_obra', 'construcao_civil', 'memorial_descritivo', 'keyword:OBRA', 'keyword:CONSTRUCAO', 'keyword:MEMORIAL DESCRITIVO'] | PROACTIVE_INSTITUTIONAL_PROSPECT | — |
| 7 | MUNICÍPIO DE SANGÃO | 12882 | 1 | ['pavimentacao', 'drenagem_works', 'memorial_descritivo', 'drenagem_works_context', 'keyword:PAVIMENTACAO', 'keyword:ENGENHARIA', 'keyword:DRENAGEM', 'keyword:MEMORIAL DESCRITIVO'] | PROACTIVE_INSTITUTIONAL_PROSPECT | — |
| 8 | PREFEITURA MUNICIPAL DE PONTE SERRADA - SC | 10649 | 1 | ['memorial_descritivo', 'planilha_orcament', 'keyword:REFORMA', 'keyword:MEMORIAL DESCRITIVO', 'keyword:PLANILHA ORCAMENTARIA'] | PROACTIVE_INSTITUTIONAL_PROSPECT | — |
| 9 | MUNICÍPIO DE PAULO LOPES | 9063 | 1 | ['obra_de', 'execucao_obra', 'pavimentacao', 'projeto_basico', 'memorial_descritivo', 'planilha_orcament', 'drenagem_works_context', 'keyword:OBRA', 'keyword:PAVIMENTACAO', 'keyword:DRENAGEM', 'keyword:PROJETO BASICO'] | PROACTIVE_INSTITUTIONAL_PROSPECT | — |

## Supplier regression

- Missing snapshot → exit 1 fail-closed (expected)
- Snapshot present (dump path may be host-local) → exit 1 fail-closed (preserves supplier gates)

## Human action (handoff)

**Tiago deve revisar a fila de órgãos, os conflitos de interesses, as classificações jurídicas preliminares, os dossiers e os materiais de abordagem antes de autorizar qualquer contato.**

Artifacts:
- `output/confenge-commercial/public-agencies/`
- `artifacts/campaigns/CONFENGE-PUBLIC-AGENCY-TECHNICAL-SERVICES-01/`
- PR #185 — do not merge until human review

## Legal disclaimer

Only `POTENTIALLY_ELIGIBLE_FOR_DIRECT_CONTRACTING`. Never claims dispensa garantida / órgão pode contratar / sem licitação.
