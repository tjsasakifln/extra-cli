# PROCESS-DOCS-01 — Delivery package (#184) + PR #133 rebase

Generated: 2026-07-31T00:13:35.946560+00:00  
HEAD #184: `50ef2a5aa8c208e9e4c90ff7e3afaa2caafc6954`  
HEAD #133 rebased: `3921aa355c1ad9c103bf97a6e1fa800e602e9c53`

## candidate_complete
**false**

## Capability metrics (independent, full denominators)

| Metric | Result | Target | Meets |
|--------|--------|--------|-------|
| discovery | 100% | 100% | yes |
| operational actives | 96.56% | ≥95% | yes |
| process recall | 100% | ≥98% | yes |
| financial | 100% | ≥99% | yes |
| notice | 99.94% | ≥98% | yes |
| session | 99.94% | ≥95% | yes |
| winning proposal | **8.91%** | ≥85% | **no** (PO residual accepted) |
| qualification | **1.27%** | ≥70% | **no** (PO residual accepted) |

`coverage --full` exit **6**.

## #137 / #133
- **#137 CLOSED** with PO residual acceptance + corpus/GT/FP-FN evidence
- **#133 rebased** onto main (MERGEABLE); bid_readiness 28/28 green
- Full suite local: 3016 passed / 14 failed — **same failures on origin/main** (env/DB fixtures)
- #133 **not** marked ready/merged; needs CI green on exact HEAD

## READY_TO_SUBMIT
**forbidden**

## PR
- #184: https://github.com/tjsasakifln/extra-cli/pull/184
- #133: https://github.com/tjsasakifln/extra-cli/pull/133
