# Integration notes — swap CONTRACT_FIXTURE producers after merge

This slice ships fail-closed consumers against **labeled fixtures**.
`producer_status=CONTRACT_FIXTURE` and `official_live=false` on every golden
file. extra-cli#400 stays open until a live proof exists.

Do not cherry-pick producer engines from #414 / #415 / #302 branches.

## How to replace each fixture

### #414 score — `contract-publication-candidate/1.0`

Current path:
`tests/fixtures/public_read_consumers/producers/contract-publication-candidate-414.json`

After the #414 PR merges, replace the fixture with the official export of the
same schema. Required fields the adapter already reads:

| adapter field | official document field |
|---|---|
| `analysis_candidate_id` | `analysis_candidate_id` or `candidate_id` |
| `canonical_contract_ids` | `canonical_contract_ids` |
| `value` | `publication_value_score.value` or `score.value` |
| `version` | `version` / `contract_version` ∈ {`1.0`,`v1.0.0`} |
| `schema` | `contract-publication-candidate/1.0` |
| `formula_version` | `publication-value-score/1.0` |
| `reason_summary` | `reason_summary` or first `reason_codes` |
| `angle` | `angle` or `suggested_analysis_angles[]` |
| `status` | `status` / `candidate_state` (`rejected` → `DATA_REJECT`) |

Do not recompute the score in this namespace.

### #414 evidence pack — `contract-evidence-pack/1.0`

Current path:
`tests/fixtures/public_read_consumers/producers/contract-evidence-pack-414.json`

Swap in the official pack. Required fields:

| adapter field | official document field |
|---|---|
| `content_hash` | `content_hash` |
| `source_as_of` | `source_as_of` or `as_of` |
| `timeline` | `timeline[]` (`at`/`event`) |
| `calculations` | `calculations[]` with `epistemic_class` |
| `official_refs` | `official_refs` / `source_refs` (url + hash) |
| `limitations` | `limitations[]` |
| `coverage` | `coverage` |
| `document_set_hash` | `document_set_hash` |
| `object` / `organ` / `supplier` / `location` | identity / parties |

Absence of `content_hash` or `source_as_of` is `producer_missing`.

### #415 peer group — `comparable-contracts/1.0`

Current path:
`tests/fixtures/public_read_consumers/producers/comparable-contracts-415.json`

Official documents emit `COMPARABLE | HOLD_FOR_DATA | NOT_COMPARABLE` and have
no `valid` field. Mapping stays:

| #415 status | consumer `peer_group.status` |
|---|---|
| `COMPARABLE` | `PEER_VALID` |
| `HOLD_FOR_DATA` | `PEER_WEAK` |
| `NOT_COMPARABLE` / absent | `NOT_COMPARABLE` / `ABSENT` |

`NOT_COMPARABLE` is informational. It does not by itself reject a usable
score + evidence pack.

### #302 claim gate — `national_universe/1.0`

Current paths:

- `tests/fixtures/public_read_consumers/producers/claim-gate-302-fail.json`
- `tests/fixtures/public_read_consumers/producers/claim-gate-302-pass.json`

After #302 can emit a live PASS, replace `claim-gate-302-pass.json` with that
document. The Market Answer consumer reads only:

| field | rule |
|---|---|
| `nacional_completo` | required true for national geography |
| `national_claim_allowed` | required true for national geography |
| `reason_codes` | propagated |
| Extra 1093 | never accepted as national denominator |

A PASS fixture does **not** authorize a production BR claim. Only a live
#302 document with `official_live=true` does.

Sibling #417 emits `authorization_state` (`AUTHORIZED` / `AUTHORIZED_WITH_LIMITATIONS`
/ `NEEDS_DATA` / `STALE` / `BLOCKED` / `FAILED`) plus `nacional_completo`.
It does **not** emit `national_claim_allowed`. Until EXTRA-011 maps
`authorization_state == AUTHORIZED` onto that flag **and** the document is
live (`official_live=true`), a missing flag stays fail-closed (`allowed=false`).
`AUTHORIZED_WITH_LIMITATIONS` already forces `nacional_completo=false` on the
producer. Extra 1093 remains a hard refuse on both sides.

## EXTRA-011 — live inputs still absent

This merge is engine-only. EXTRA-011 must not treat fixture / preview / dry-run
as live proof. Required live inputs, none of which this slice supplies:

| Input | Source PR / issue | What EXTRA-011 still needs |
|---|---|---|
| Pack + score live | #419 / #414 | Official `contract-publication-candidate/1.0` + `contract-evidence-pack/1.0` with `official_live=true` (not the CONTRACT_FIXTURE files under `tests/fixtures/public_read_consumers/producers/`) |
| Peer group live | #418 / #415 | Official `comparable-contracts/1.0` with `COMPARABLE\|HOLD_FOR_DATA\|NOT_COMPARABLE` and `official_live=true` |
| National gate live | #417 / #302 | Live arbiter document with `official_live=true` **and** `nacional_completo` authorized (`authorization_state=AUTHORIZED` on the versioned national universe). Map that to `national_claim_allowed` here; do not accept Extra 1093, ICP, or row count as the national denominator. |

`DATA_READY` still does not authorize `INDEX` / `PUBLISHABLE_*`.
#400 stays open until those live documents exist and are bound.

## Proposed shared-view SQL (not a migration)

No migration ships in this PR. If `public_read_v1` later needs a dedicated
family, apply something like the following **after** architects agree and a
free migration number is reserved:

```sql
-- PROPOSAL ONLY. Do not apply from this branch.
-- SELECT-only family for named consumers, reusing existing snapshot facts.
-- CREATE VIEW public_read_v1.consumer_contract_analysis AS
-- SELECT analysis_candidate_id, canonical_contract_id, as_of, completeness
-- FROM <existing READY_CANONICAL projection>
-- WHERE ...;
```

Until that exists, consumers bind fixture/official JSON documents and the
existing `public_read_v1.contracts` / `research_claim_gate` families.

## What this branch must not do

- copy producer engines from other worktrees;
- close extra-cli#400;
- schedule a crawler when a consumer changes;
- emit `official_live=true` from a fixture.
