# Final report — CONFENGE-PUBLIC-AGENCY-TECHNICAL-SERVICES-01

**Status:** `READY_FOR_TIAGO_REVIEW_PUBLIC_AGENCY_VERTICAL`  
**PR:** https://github.com/tjsasakifln/extra-cli/pull/185  
**Run SHA (dual launch = tip):** `aba9db86317aa63d0376348f0cc2f69670e981cf`  
**Updated (UTC):** 2026-07-31T00:32:49Z

## Structural eng-match fix (occupancy absolute + obra de arte)

Multi-tier `classify_engineering_object`:

1. **OCCUPANCY hard-neg absolute** (concessão/cessão/permissão de uso) — never overridden by soft `OBRA DE` or true works-execution rescue.
2. Cultural / labor / pageant / supply hard-negatives.
3. **STRONG_WORKS** only (negative complements: ARTE/TEATRO/INFRAESTRUTURA EXISTENTE blocked).
4. WEAK_NOUN_ONLY / KEYWORD_ONLY never publish alone.

Profile keywords never force True. Publishable leads require ≥1 evidence with `eng_tier=STRONG_WORKS`.

Golden corpus + pipeline not-publishable fixtures cover occupancy+OBRA DE and obra-de-arte skeptic FPs.

## Dual launch

| Metric | Value |
|--------|-------|
| evaluated | 276 |
| publishable | 9 |
| top_n (honest, not padded) | **9** |
| no_weak_false_eng | true |
| dual names equal | true |
| Xanxerê concessão | excluded |
| Palmitos pageant | excluded |
| Fundação Cultural SBS (weak obra/reforma) | dropped after occupancy/arte gate |
| padded_to_20 | false |

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

Fail-closed without authenticated snapshot manifest (expected; preserves supplier modality).

## Human action (handoff)

**Tiago deve revisar a fila de órgãos, os conflitos de interesses, as classificações jurídicas preliminares, os dossiers e os materiais de abordagem antes de autorizar qualquer contato.**

Artifacts for review:
- `output/confenge-commercial/public-agencies/` (dossiers/, commercial-kit/, leads, conflict-review, compliance-flags)
- `artifacts/campaigns/CONFENGE-PUBLIC-AGENCY-TECHNICAL-SERVICES-01/`
- PR #185 — do not merge until human review

## Legal disclaimer (fail-closed)

Only status used: `POTENTIALLY_ELIGIBLE_FOR_DIRECT_CONTRACTING` when thresholds and object class allow.  
Never claims: dispensa garantida / órgão pode contratar / sem licitação.
