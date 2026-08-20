# public-read-bid-readiness/1.0

Fail-closed producer that composes **edital_case**, **budget_audit**,
**technical_acervo**, and **bid_readiness** into a private coverage envelope.
Future consumer: `web-cfg#155`. This contract is not a landing page, index
grant, upload endpoint, or publication authority. It does not close #155.

Machine-readable twin: [`public-read-bid-readiness-v1.json`](public-read-bid-readiness-v1.json)
Payload schema: [`public-read-bid-readiness-v1.schema.json`](public-read-bid-readiness-v1.schema.json)

## Decide

Given explicit local paths (or an authorized manifest) the producer:

1. refuses unsafe inputs **before** any PDF/XLSX parser (`REJECT`);
2. runs four existing engines as adapters (no second extraction engine);
3. maps each finding to `FACT` | `RISK` | `UNKNOWN`;
4. returns exactly one `overall_state`:

`READY_FOR_HUMAN_REVIEW` · `HOLD_FOR_DATA` · `REJECT`

Human review is always required. Absence never becomes a silent negative.
`FACT` without evidence hash or locator is refused. `RISK` without method/rule
is refused.

## Fail-closed rules

- Missing edital, planilha, documents, acervo, unreadable PDF, incomplete
  document, unavailable engine, or insufficient coverage → `UNKNOWN` findings
  and `HOLD_FOR_DATA`. No invented approval.
- Path traversal, zip bomb, oversized file, disallowed type, malware-like
  payload → `REJECT` before parse.
- `RISK` is a technical condition for human review. It is not illegality,
  ineligibility, or inexequibility.
- Default path is deterministic. No unapproved LLM. Unavailable provider →
  `UNKNOWN` / `HOLD_FOR_DATA`.
- `publication_authorization` and `index_authorization` remain `false`.
- Consumer fixture is SELECT/read-only and does not authorize a page.

## Envelope (minimum)

- `schema_version` = `public-read-bid-readiness/1.0`
- `run_id` / `query_id` (deterministic)
- `generated_at`, `as_of`, `expires_at`
- `input_manifest` of hashes/types/sizes (no file content)
- engine/module/policy versions
- `source_access` = `private_local` | `redacted_fixture`
- `overall_state` in the closed trio
- `human_review_required` = true
- `not_legal_conclusion` = true
- `publication_authorization` = false
- `index_authorization` = false
- `content_hash`, `limitations`, `prohibited_claims`
- findings with state, statement, non-sensitive `source_document_id`, locator,
  evidence hash/ref, confidence/coverage, reason codes, contradiction links,
  interpretive limit
- summary: covered, missing, conflicts, unevaluated, blockers, human next
  steps, observable review cost/time (never a win estimate)

## CLI

```bash
python3 -m scripts.bid_readiness_public run \
  --edital PATH --planilha PATH --documents PATH \
  --acervo PATH --requirements PATH \
  --as-of 2026-08-20T12:00:00+00:00 \
  --work-dir /tmp/bid-readiness-public \
  --out envelope.json --public-out fixture.public.json
```
