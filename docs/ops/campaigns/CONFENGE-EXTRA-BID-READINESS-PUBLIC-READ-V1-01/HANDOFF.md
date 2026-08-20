# CONFENGE-EXTRA-BID-READINESS-PUBLIC-READ-V1-01

Producer-only, private/manual-first wave. Exclusive worktree.
Future consumer: **web-cfg #155** (not closed).

## Terminal

```
CAMPAIGN=CONFENGE-EXTRA-BID-READINESS-PUBLIC-READ-V1-01
BASE_SHA=9c5e7d47f99902d9d97cf479aefbba8cd391a14d
FINAL_HEAD_SHA=87ff36008ab88f4f85c7900d3a91519ff7ce7302
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
TESTS=tests/bid_readiness_public 31 passed; reused edital_case 34, budget_audit 21, technical_acervo 25, bid_readiness 35
CI=opened-on-pr-442
MERGED=false
DEPLOYED=false
FINAL_VERDICT=PUBLIC_READ_V1_READY_FOR_WEB_CONSUMER_IMPLEMENTATION
EXACT_RESIDUALS=engine CLIs remain campaign-isolated (adapters use library entry points); default extra acervo path refused; bid_readiness BLOCKED_* mapped into the public-read trio; empty engine locators degrade FACT to UNKNOWN
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

## Handoff to web-cfg #155

SELECT-only read model:

`exports/public-read-bid-readiness/1.0/web-cfg-155-read-model.sql`

Do not close #155. Do not claim 10 real-case conclusions or a commercial conversation.
