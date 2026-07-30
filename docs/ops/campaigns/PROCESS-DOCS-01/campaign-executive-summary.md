# Campaign PROCESS-DOCS-01 — Executive Summary

Generated: 2026-07-30T19:32:17.477706+00:00

## Capability
`procurement_process_documents` — discovery, collection, preservation, classification and audit of public administrative process documents for the 1.093-entity Extra/CONFENGE universe.

## Metrics (independent — no average)

| Metric | Value | Threshold | Meets |
|--------|-------|-----------|-------|
| entity_source_discovery_coverage | 100.0% (1093/1093) | 100% | True |
| active_entity_document_operational_coverage | 82.3096% (335/407) | ≥95% | False |
| relevant_process_recall | 0.0% (0/0) | ≥98% | False |
| covered_financial_value_ratio | 0.0% | ≥99% | False |
| notice_and_annexes_completeness | 0.0% | ≥98% | False |
| session_judgment_homologation_completeness | 0.0% | ≥95% | False |
| winning_proposal_completeness | 0.0% | ≥85% | False |
| bidder_qualification_documents_completeness | 2.7778% | ≥70% | False |

Gate exit code for full bundle: **3** (non-zero = not ready to claim completion).

## Activity
- Active: 407
- Inactive: 1
- Pending independent evidence: 685

## Live proof
- CIGA CKAN adapter: SUCCESS_NONZERO at scale for municipal DOM-SC packages (shared public ZIPs, CAS).
- Generic HTML: partial success against sc_compras / compras.gov / institutional seeds.
- PNCP adapter: implemented + unit/contract tested; **live blocked** in this environment (timeout / remote disconnect).

## Corpus / bid_readiness
- Processes in corpus: 81
- Engineering: 0
- Complete envelopes: 67
- Portal families: 2
- Annotated requirement slots: 1422
- issue_137_unblock_allowed: **False**
- READY_TO_SUBMIT language: **forbidden** without human review

## Gaps (honest)
- Operational coverage below 95%: remaining active entities blocked on PNCP unavailability, auth, or missing entity-specific portals.
- Process recall / financial coverage not claimable: independent benchmark empty until sealed inventory.
- Completeness below targets: public packs are mostly DOM publications, not full bid envelopes.

## What is NOT claimed
- LOCAL_READY / VPS_OPERATIONAL / PROJECT_DONE
- 95% operational document coverage
- 98% process recall / 99% financial
- Closing issue #137 / unblocking PR #133
