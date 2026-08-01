# PR #187 Consumer Contract Report

## Status

| Layer | Status |
|-------|--------|
| **Schema / snapshot contract vs web-cfg rules** | **PROVEN** |
| **Render/build (`npm run pseo:build`) / Netlify** | **`CONSUMER_INTEGRATION_NOT_PROVEN`** |
| **Write into web-cfg tree from extra-cli** | **FORBIDDEN** (read-only verifier only) |

## Method
1. Read-only fetch of `tjsasakifln/web-cfg` contracts:
   - `docs/pseo/DATA-CONTRACT.md`
   - `scripts/pseo/schema.py`
   - `scripts/pseo/tests/test_schema_compat.py`
2. Vendored consumer rules under `tests/pseo/consumer_web_cfg/` (no write to web-cfg).
3. Fixture export from extra-cli → `validate_consumer_snapshot()`.
4. B1: `scripts/pseo/verify_web_cfg_compat` — changelog/notes only under extra-cli `--out`; adversarial tree hash equality.

## Proven checks
- Required files present
- `schema_version` ∈ {1.0.0, 1.1.0}
- Manifest required fields
- Checksums match
- `dataset_hash` recomposes with consumer algorithm
- Forbidden commercial JSON patterns rejected (adversarial test)
- Consumer tree remains byte-identical after all verifier options (no apply/build)

## Tests
- `tests/pseo/test_consumer_contract.py`
- `tests/pseo/test_web_cfg_readonly.py`

## Non-claims
- No Netlify deploy
- No production `data/pseo/` mutation
- No full web-cfg site render pipeline in CI of extra-cli
- No auto-publish; `PUBLISH_READY` ≠ `MERGE_READY`
