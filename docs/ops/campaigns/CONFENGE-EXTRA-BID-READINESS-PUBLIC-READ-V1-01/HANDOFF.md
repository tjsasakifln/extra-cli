# CONFENGE-EXTRA-BID-READINESS-PUBLIC-READ-V1-01

Producer-only, private/manual-first wave. Exclusive worktree.
Future consumer: **web-cfg #155** (not closed).

## Terminal

```
CAMPAIGN=CONFENGE-EXTRA-BID-READINESS-PUBLIC-READ-V1-01
BASE_SHA=9c5e7d47f99902d9d97cf479aefbba8cd391a14d
ORIGINAL_REVIEW_HEAD_SHA=87ff36008ab88f4f85c7900d3a91519ff7ce7302
PR=https://github.com/tjsasakifln/extra-cli/pull/442
SCHEMA=public-read-bid-readiness/1.0
CLI=python3 -m scripts.bid_readiness_public
MODULES_REUSED=edital_case,budget_audit,technical_acervo,bid_readiness
OVERALL_STATES=READY_FOR_HUMAN_REVIEW|HOLD_FOR_DATA|REJECT
PUBLIC_FIXTURE_KIND=redacted_fixture
REAL_DOCUMENTS_IN_GIT=0
PII_HITS=0
FORBIDDEN_CLAIM_HITS=0
PUBLICATION_AUTHORIZATION=false
INDEX_AUTHORIZATION=false
HUMAN_REVIEW_REQUIRED=true
DETERMINISTIC_REPLAY=true
TESTS=tests/bid_readiness_public 40 passed; reused engine suites 115 passed; total 155 passed
CI_STATUS_AT_HANDOFF=pending-adversarial-fix-head
MERGED_AT_HANDOFF=false
DEPLOYED_AT_HANDOFF=false
FINAL_VERDICT=LOCAL_GATES_PASS__EXACT_HEAD_CI_AND_ADVERSARIAL_REREVIEW_REQUIRED
EXACT_RESIDUALS=engine CLIs remain campaign-isolated (adapters use library entry points); default extra acervo path refused; bid_readiness BLOCKED_* mapped into the public-read trio; empty engine locators degrade FACT to UNKNOWN; public export requires an integrity-valid redacted_fixture
```

## Semantics

- extra-cli owns facts, extraction, evidence, state, reason codes.
- extra-cli does not own public UX, CTA, indexation, or commercial GO.
- extra-cli does not write web-cfg and does not authorize final GO.
- `READY_FOR_HUMAN_REVIEW` is coverage sufficient for a human go/no-go, not `READY_TO_SUBMIT`.

## Residuals (nominal, adapter-mapped)

- Engine CLIs remain campaign-isolated; adapters call library entry points (`run_pipeline(..., isolation_ok=True)`, `extract_pdf`/`extract_txt`, `read_workbook`+`workbook_integrity`, `match_requirement`). Isolation CLIs are not composed.
- `technical_acervo` default store `data/extra_technical_acervo.json` is refused; an explicit fictional path is required.
- `bid_readiness` terminals `NOT_READY`/`BLOCKED_*` stay inside that engine and are mapped into the public-read trio (not a second classifier).
- `bid_readiness` findings often have empty `source_locators`; the adapter fills from requirement locators or degrades FACT to UNKNOWN.
- Engine impact copy that mentioned eligibility risk is rewritten at the adapter boundary.
- Authorized manifest paths are checked by path ancestry, not string prefix;
  manifests and entity JSON are preflighted before parse.
- Entity input is bound into the input manifest/query identity. Envelope hashes
  are recomputed on validation.
- Public export is fail-closed: `private_local` is refused, known PII/signature
  markers are re-redacted, and the result is scanned before write.

## Handoff to web-cfg #155

SELECT-only read model:

`exports/public-read-bid-readiness/1.0/web-cfg-155-read-model.sql`

Do not close #155. Do not claim 10 real-case conclusions or a commercial conversation.
