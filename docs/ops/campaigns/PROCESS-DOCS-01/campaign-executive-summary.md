# PROCESS-DOCS-01 — Evidence review pass (GT + win/qual residual)

Generated: 2026-07-30T23:41:25.664833+00:00

## Independent metrics (full denom, no shrink)

| Metric | Result | Target | Gate |
|--------|--------|--------|------|
| discovery | 100% | 100% | **MET** |
| operational | 96.56% | ≥95% | **MET** |
| recall | 100% | ≥98% | **MET** |
| financial | 100% | ≥99% | **MET** |
| notice | 99.94% | ≥98% | **MET** |
| session | 99.94% | ≥95% | **MET** |
| winning proposal | **8.91%** | ≥85% | **OPEN** |
| qualification | **1.27%** | ≥70% | **OPEN** |

`coverage --full` exit **6**.

## GT evidence review (600 slots)
- All **600** slots evidence-reviewed
- Labels: **present × 600** (CAS/run-index verified)
- Flagged: **0**
- Reviewer: `process_documents.confirm_gt_review`
- Method: cas_presence_process_linkage_title_category
- **`product_owner_signoff=false`**
- **`human_ground_truth_complete=false`**
- **`issue_137_close_allowed=false`**
- **READY_TO_SUBMIT forbidden**

This pass is evidence review of document presence, **not** Tiago product-owner sign-off for bid_readiness.

## Win/qual residual blocker review (nominal, in denom)
| Blocker | Count |
|---------|------:|
| sc_compras_homolog_without_public_proposal_pack | 2400 |
| session_public_but_winning_proposal_pdf_not_published | 526 |
| non_process_publication_dump (win) | 19 |
| session_public_but_bidder_qualification_not_published | 3179 |
| non_process_publication_dump (qual) | 14 |

**Decision:** leave win/qual gates open. No denom shrink.

## Explicit non-claims
- `candidate_complete = false`
- Issue **#137 OPEN**
- PR **#133 blocked**
- No READY_TO_SUBMIT language

## Evidence files
- `vps/evidence-review-pass-summary.json`
- `vps/residual-win-qual-blocker-review.json`
- `vps/bid-readiness-human-gt-manifest.json`
- `vps/bid-readiness-fp-fn-report.json`
- `vps/honest-residual-final.json`

## PR
https://github.com/tjsasakifln/extra-cli/pull/184
