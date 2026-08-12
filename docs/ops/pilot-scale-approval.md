# Pilot scale approval

Any document collection queue or decision package with more than 30 entities
is fail-closed until a human-approved pilot artifact passes the preflight in
`scripts.ops.multi_source_open_pack.pilot_gate`.

The approval is external evidence, not a generated repository fixture. Pass it
with `--pilot-approval /path/to/pilot-approval.json` or set
`EXTRA_PILOT_APPROVAL` for the weekly/document operational paths.

## Required contract

The JSON must use `schema_version=pilot-scale-approval/v1` and contain:

- exactly 30 unique `entities`, all members of the active universe;
- at least two non-empty `stratum` values;
- at least two unique declared `sources`; every one of the 30 entities must
  contain exactly one result for every declared source, with no missing,
  duplicate, or undeclared source;
- for every entity/source result: completed request and scope, complete page
  counts with `pages_fetched == pages_expected`, record count, `success_zero`
  or `not_zero`, and a reconciled deduplication count whose `output_records`
  equals `records`;
- an existing evidence file and its full SHA-256 for every source result;
- full SHA-256 values for `config/target_entities_200km.csv` and
  `config/source_applicability.yaml`;
- `human_approval.status=APPROVED`, `approved_by`, and `approved_at`.

Abbreviated illustration (it is not valid until all 30 rows and both declared
source results per row are present):

```json
{
  "schema_version": "pilot-scale-approval/v1",
  "universe_sha256": "<64 hex>",
  "policy_sha256": "<64 hex>",
  "sources": ["pncp", "ciga_ckan"],
  "entities": [
    {
      "entity_id": "82922233",
      "stratum": "municipal-near",
      "source_results": [
        {
          "source": "pncp",
          "request_completed": true,
          "scope_complete": true,
          "pagination": {"complete": true, "pages_fetched": 2, "pages_expected": 2},
          "records": 4,
          "zero_proof": "not_zero",
          "deduplication": {
            "complete": true,
            "input_records": 5,
            "output_records": 4,
            "duplicates_removed": 1
          },
          "evidence_path": "evidence/82922233-pncp.json",
          "evidence_sha256": "<64 hex>"
        }
      ]
    }
  ],
  "human_approval": {
    "status": "APPROVED",
    "approved_by": "<human reviewer>",
    "approved_at": "<ISO-8601 timestamp>"
  }
}
```

Relative evidence paths are resolved from the approval artifact directory.
Zero-page pagination is valid only as `pages_fetched=pages_expected=0` with
`records=0`, `success_zero`, and zero deduplication output; an empty first page
represented as `1/1` with zero records remains valid as well.
Changing either the universe or source-applicability policy invalidates an old
approval. A missing, malformed, mismatched, or self-incomplete artifact stops
before package output or queue state is created.
