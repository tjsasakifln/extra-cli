# PROCESS-DOCS-01 — Executive Summary (win/qual + structural GT)

Generated: 2026-07-30T23:35:51.209733+00:00

## Metrics (full denominators, no shrink)

| Metric | Result | Target | Meets |
|--------|--------|--------|-------|
| discovery | 100% | 100% | yes |
| operational | 96.56% | ≥95% | yes |
| recall | 100% | ≥98% | yes |
| financial | 100% | ≥99% | yes |
| notice | **99.94%** | ≥98% | **yes** |
| session | **99.94%** | ≥95% | **yes** |
| winning proposal | **8.91%** (288/3234) | ≥85% | no |
| qualification | **1.27%** (41/3234) | ≥70% | no |

Gate exit **6**.

## Win/qual multi-source this wave
- PNCP `/itens/n/resultados` for residual win gaps (350 processes)
- ZIP expand 200 packs → 1267 members
- Classifier: generic `anexo` upgraded when title = planilha das licitantes / proposta
- Qual: minimal public yield (HTML/PNCP/zip)

## Residual honesty (stay in denominator)
- win: 2946 × `winning_proposal_not_published_publicly`
- qual: 3193 × `bidder_qualification_not_published_publicly`

## bid_readiness GT / FP-FN
- **600** slots structural-labeled from CAS presence (`present`×600)
- `label_source=automated_structural_from_cas`
- `human_confirmed=0`, `human_ground_truth_complete=false`
- FP candidates: 138 (sparse pack auto-submit risks)
- **READY_TO_SUBMIT forbidden**
- **Issue #137 NOT closed**

## PR
https://github.com/tjsasakifln/extra-cli/pull/184
