# FINAL REPORT — CONFENGE Unconditional GO campaign

Generated: `2026-08-10T04:10:11Z`

## Historical contaminated evidence (INVALID — do not reuse)

- Prior claim: EMAIL_SEND_READY=62 with WRONG_CONTACT=0
- Contained `licitacoes@demo00Xobra.com.br` labeled COMPANY_OWNED+VERIFIED on real CNPJs
- Invalidated: `INVALIDATED_REASON=PROVENANCE_CONTAMINATION`
- See CONTAMINATION-ERADICATION.json, COHORT-62-INVALIDATION.json

## New clean evidence

- Distinct clean companies: **53**
- First-50 audit counters: all zero (FALSE_TARGET, WRONG_CONTACT, UNSUPPORTED_SERVICE, HOLLOW_COPY, UNSAFE_CLAIM, DEMO_OR_FIXTURE, TAINTED_PROVENANCE)
- Provenance gate: recompute fail-closed; sticky VERIFIED never washes taint
- Warmbly production: contaminated_sendable_count=**0**, demo blocked=9
- Target-fit continuous: module deployed, migration 071 applied, STATUS=**HEALTHY**, watermarks equal, SHADOW mode

## Code changes

### extra-cli
- `scripts/confenge_contact_resolution/provenance_trust.py` (new)
- send_readiness / ownership / human_review / warmbly_bridge.mapping
- Permanent suite `tests/confenge_contact_resolution/test_provenance_contamination.py`
- Target-fit continuous rebased onto main + provenance (#212)

### warmbly
- `internal/app/confenge/provenance_taint.go` + import/CanEnroll gates
- PR #35

## Terminal

See GO-NO-GO.md — **EXTERNAL_BLOCKER_REQUIRES_TIAGO** for human review sample only.
