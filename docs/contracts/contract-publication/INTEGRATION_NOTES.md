# Integration notes — #414 producer → #400 / #415

Owner of this namespace: `scripts/contract_publication/**`.
This file records interfaces this producer expects. It does not implement
comparables (#415), public-read adapters (#400) or national claims (#302).

## Expected by #400 (`public-read-contract-analysis/1.0`)

This producer emits:

| Artifact | Schema / version |
|---|---|
| Candidate / score | `contract-publication-candidate/1.0` + `publication-value-score/1.0` |
| Evidence pack | `contract-evidence-pack/1.0` (alias `contract_evidence_pack/1.0`) |
| Consumer bundle | `public-read-contract-analysis/1.0` via `export-400` |

`data_state` is only `DATA_READY | DATA_HOLD | DATA_REJECT`.
This producer never emits `INDEX` or `PUBLISHABLE_*`.

Score payload the adapter already reads:

- `publication_value_score.value` (null = UNKNOWN, never coerced to 0)
- `schema`, `contract_version`, `score_formula_version`
- `candidate_state`
- `reason_codes` / `reason_summary`
- `canonical_contract_id` / `analysis_candidate_id`

The adapter Goal 03 may still be on a sibling branch. This producer does
not edit `scripts/public_read/**`. When that adapter lands, point it at
`export-400/analyses/*.json` or at `candidates.json` + `packs/*.json`.

## Expected from #415 (`comparable-contracts/1.0`)

Peer input is accepted only when `peer_group.schema` is
`comparable-contracts/1.0` or `public-read-comparable-contracts/1.0`.

Accepted producer statuses: `COMPARABLE | HOLD_FOR_DATA | NOT_COMPARABLE`.
Mapped for #400 as `PEER_VALID | PEER_WEAK | NOT_COMPARABLE`.

Missing or unversioned peer → `UNKNOWN` / `ABSENT`. `NOT_COMPARABLE` is
informational and does not, by itself, reject a defensible pack.

Until #415 merges, use a labeled fixture `peer_group` with
`catalog_mode=fixture`. Never promote that fixture to official.

## What this producer will not do

- Query or mutate Goal 02 comparable engines.
- Write Goal 03 read-model adapters.
- Touch national-claims / Goal 04 modules.
- Create migrations.
- Call an LLM as a factual authority.
