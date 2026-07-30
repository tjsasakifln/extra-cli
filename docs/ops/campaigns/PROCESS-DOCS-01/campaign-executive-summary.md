# PROCESS-DOCS-01 — Executive Summary (gap-close + completeness raise)

Generated: 2026-07-30T22:12:53.069476+00:00

## Capability
`procurement_process_documents`

## Metrics (independent — no average)

| Metric | Result | Target | Meets |
|--------|--------|--------|-------|
| discovery | 100% (1093/1093) | 100% | yes |
| operational actives | **96.56%** (393/407) | ≥95% | **yes** |
| process recall | **100%** (807/807) | ≥98% | **yes** |
| financial coverage | **100%** | ≥99% | **yes** |
| completeness edital/anexos | **89.83%** binary | ≥98% | no |
| completeness julgamento | **7.66%** | ≥95% | no |
| completeness proposta | **3.83%** | ≥85% | no |
| completeness habilitação | **3.83%** | ≥70% | no |

`coverage --full` exit **6** (completeness only).

### Completeness methodology (2026-07-30)
- Process-level **binary presence** after title/filename reclassification (not category-fraction).
- 77 noise processes excluded (CIGA publication dumps / numeric-only opaque titles).
- 757 scorable processes; notice raised ~8% → **89.8%** via classifier expansion (DFD, ETP, TR_, PE, EDITAL\d, dispensa, etc.).
- Session / proposal / qualification remain **publication-limited** on PNCP arquivos (honest residual).

## Residual operational gaps
14 active entities remain **blocked** in the operational denominator (no public process pack after targeting). Not removed from denominator.

## Corpus
- processes: 889
- engineering: 80
- envelopes: 412
- families: 6
- annotations: 5657

## bid_readiness / #137
- FP/FN: automated structural candidates + human review queue scaffold
- **READY_TO_SUBMIT forbidden**
- Issue #137 **not closed** (needs human ground truth)

## VPS
- timer `extra-process-documents-incremental.timer` enabled
- code at `/opt/extra-consultoria/scripts/process_documents`
- evidence under `/var/lib/extra-consultoria/output/process_documents`
- PR: https://github.com/tjsasakifln/extra-cli/pull/184
