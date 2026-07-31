# Final report — CONFENGE-PUBLIC-AGENCY-TECHNICAL-SERVICES-01

**Status:** `READY_FOR_TIAGO_REVIEW_PUBLIC_AGENCY_VERTICAL`  
**PR:** https://github.com/tjsasakifln/extra-cli/pull/185  
**Run SHA (dual launch = tip):** `c4eb60c82d741d4dc3e74e33c23821ff8970c0b2`  
**Updated (UTC):** 2026-07-31T00:10:22Z

## Structural eng-match fix

Multi-tier `classify_engineering_object`: HARD_NEGATIVE → STRONG_WORKS → WEAK_NOUN_ONLY → KEYWORD_ONLY.  
Profile keywords never force True. Publishable leads require ≥1 evidence with `eng_tier=STRONG_WORKS`.

## Dual launch

| Metric | Value |
|--------|-------|
| evaluated | 275 |
| publishable | 10 |
| top_n (honest, not padded) | **10** |
| no_weak_false_eng | true |
| Xanxerê concessão | excluded |
| Palmitos pageant | excluded |

## Top 10

| # | Órgão | Pop | #STRONG_WORKS | reasons | Mode | Oferta |
|---|-------|-----|---------------|---------|------|--------|
| 1 | MUNICÍPIO DE ITAIÓPOLIS | 22051 | 1 | ['obra_de', 'execucao_obra', 'pavimentacao', 'drenagem_works', 'drenagem_works_context', 'keyword:OBRA', 'keyword:PAVIMENTACAO', 'keyword:DRENAGEM'] | PROACTIVE_INSTITUTIONAL_PROSPECT | REVISAO_PRE_PUBLICACAO |
| 2 | MUNICÍPIO DE POUSO REDONDO | 17123 | 1 | ['construcao_de', 'keyword:CONSTRUCAO'] | PROACTIVE_INSTITUTIONAL_PROSPECT | REVISAO_PRE_PUBLICACAO |
| 3 | MUNICÍPIO DE GAROPABA | 29959 | 1 | ['obra_de', 'execucao_obra', 'pavimentacao', 'keyword:OBRA', 'keyword:PAVIMENTACAO'] | PROACTIVE_INSTITUTIONAL_PROSPECT | REVISAO_PRE_PUBLICACAO |
| 4 | Prefeitura Municipal de Catanduvas | 10566 | 1 | ['memorial_descritivo', 'keyword:OBRA', 'keyword:MEMORIAL DESCRITIVO'] | PROACTIVE_INSTITUTIONAL_PROSPECT | REVISAO_PRE_PUBLICACAO |
| 5 | MUNICÍPIO DE CAMPOS NOVOS | 36932 | 1 | ['obra_de', 'execucao_obra', 'construcao_de', 'projeto_basico', 'keyword:OBRA', 'keyword:CONSTRUCAO', 'keyword:PROJETO BASICO'] | PROACTIVE_INSTITUTIONAL_PROSPECT | REVISAO_PRE_PUBLICACAO |
| 6 | MUNICÍPIO DE ÁGUAS DE CHAPECÓ | 6036 | 1 | ['obra_de', 'execucao_obra', 'construcao_civil', 'memorial_descritivo', 'keyword:OBRA', 'keyword:CONSTRUCAO', 'keyword:MEMORIAL DESCRITIVO'] | PROACTIVE_INSTITUTIONAL_PROSPECT | REVISAO_PRE_PUBLICACAO |
| 7 | PREFEITURA MUNICIPAL DE SANGÃO | 12882 | 1 | ['pavimentacao', 'drenagem_works', 'memorial_descritivo', 'drenagem_works_context', 'keyword:PAVIMENTACAO', 'keyword:ENGENHARIA', 'keyword:DRENAGEM', 'keyword:MEMORIAL DESCRITIVO'] | PROACTIVE_INSTITUTIONAL_PROSPECT | REVISAO_PRE_PUBLICACAO |
| 8 | PREFEITURA MUNICIPAL DE PONTE SERRADA - SC | 10649 | 1 | ['memorial_descritivo', 'planilha_orcament', 'keyword:REFORMA', 'keyword:MEMORIAL DESCRITIVO', 'keyword:PLANILHA ORCAMENTARIA'] | PROACTIVE_INSTITUTIONAL_PROSPECT | REVISAO_PRE_PUBLICACAO |
| 9 | MUNICÍPIO DE PAULO LOPES | 9063 | 1 | ['obra_de', 'execucao_obra', 'pavimentacao', 'projeto_basico', 'memorial_descritivo', 'planilha_orcament', 'drenagem_works_context', 'keyword:OBRA', 'keyword:PAVIMENTACAO', 'keyword:DRENAGEM', 'keyword:PROJETO BASICO'] | PROACTIVE_INSTITUTIONAL_PROSPECT | ORCAMENTO_E_PLANEJAMENTO_DE_OBRAS |
| 10 | Fundação Cultural de São Bento do Sul | 83277 | 1 | ['obra_de', 'keyword:OBRA', 'keyword:REFORMA'] | PROACTIVE_INSTITUTIONAL_PROSPECT | REVISAO_PRE_PUBLICACAO |

## Human action (handoff)

**Tiago deve revisar a fila de órgãos, os conflitos de interesses, as classificações jurídicas preliminares, os dossiers e os materiais de abordagem antes de autorizar qualquer contato.**

Artifacts for review:
- `output/confenge-commercial/public-agencies/` (dossiers/, commercial-kit/, leads, conflict-review, compliance-flags)
- `artifacts/campaigns/CONFENGE-PUBLIC-AGENCY-TECHNICAL-SERVICES-01/`
- PR #185 — do not merge until human review
