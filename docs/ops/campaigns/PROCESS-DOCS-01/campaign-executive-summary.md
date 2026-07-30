# PROCESS-DOCS-01 — Executive Summary (multi-source session)

Generated: 2026-07-30T22:39:47.366372+00:00

## Capability
`procurement_process_documents`

## Metrics (independent, full denominators)

| Metric | Result | Target | Meets |
|--------|--------|--------|-------|
| discovery | 100% (1093/1093) | 100% | yes |
| operational actives | **96.56%** (393/407) | ≥95% | **yes** |
| process recall | **100%** (807/807) | ≥98% | **yes** |
| financial coverage | **100%** | ≥99% | **yes** |
| completeness edital/anexos | **99.64%** | ≥98% | **yes** |
| completeness julgamento | **35.01%** | ≥95% | no — residual blocked |
| completeness proposta | **3.84%** | ≥85% | no — residual blocked |
| completeness habilitação | **4.56%** | ≥70% | no — residual blocked |

`coverage --full` exit **6**.

## Multi-source session wave
- PNCP `/itens` outcomes (`situacaoCompraItemNome=Homologado`) → session docs
- PNCP `/historico`, `/atas` when published
- Origin HTML + CIGA DOM attempted (limited public yield)
- Session lift: ~10% → **35%** (292/834 processes)
- Win/qual remain publication-limited (~4%)

## Corpus / bid_readiness
- processes **889** / eng **111** / envelopes **623** / families **7** / annotations **7261**
- min targets: **met**
- FP/FN: automated candidates only (`awaiting_human_ground_truth`)
- **READY_TO_SUBMIT forbidden**; issue **#137 open**

## Residual honesty
Session residual 542, win 802, qual 796 stay in denominator with blockers
`session_judgment_not_published_publicly` / `winning_proposal_not_published_publicly` /
`bidder_qualification_not_published_publicly`.

## PR
https://github.com/tjsasakifln/extra-cli/pull/184
