# web-cfg consumer contract (read-only vendored)

**Source:** `tjsasakifln/web-cfg` @ main  
**Fetched:** 2026-07-31 via GitHub Contents API (read-only)  
**Canonical docs:** `docs/pseo/DATA-CONTRACT.md`, `scripts/pseo/schema.py`

## Consumer requirements used by tests

### Required snapshot files
- manifest.json
- archetypes.json
- markets.json
- agencies.json
- prices.json
- competition.json
- opportunities.json
- problem_service.json
- schema.json

### schema_version allowlist (consumer)
- `1.0.0`
- `1.1.0`

### Manifest required fields
- generated_at, source_run_id, dataset_hash, checksums, sources, counts, freshness, limitations

### Forbidden raw JSON patterns (fail-closed)
- score_total, commercial_state, human_notes, human_decision
- suggested_offer, next_human_step, rank_position, top20, do_not_contact

### Dataset body keys for hash recompute
- archetypes, markets, agencies, prices, competition, opportunities, problem_service, icp_methodology

## Integration status

This package tests that **extra-cli fixture exports satisfy the consumer's static contract**.

It does **not** prove:
- live Netlify deploy
- `npm run pseo:build` in web-cfg
- production `data/pseo/` swap

If full renderer integration is not executed, report may still list:
`CONSUMER_INTEGRATION_NOT_PROVEN` for build/render pipeline — while marking **schema contract** as proven.
