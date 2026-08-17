# Coverage live proof (issue #350)

Hermetic, reproducible proof that **source-wide aggregated evidence is not
entity coverage**. The dual-coverage identity rules already live in
`scripts/coverage/covered_entity.py`. This campaign does **not** change
engines, thresholds, or schema. It proves those rules on a real PostgreSQL
that this runner provisions, migrates, seeds, measures, hashes, and tears down.

## Single local command

PostgreSQL must already be reachable (local compose `test-db` on 5433, CI
service, or any ephemeral cluster). The runner **creates a sibling database**
`coverage_live_proof_<12-hex>` and drops only that database.

```bash
LOCAL_DATALAKE_DSN='postgresql://test:test@127.0.0.1:5433/extra_test' \
  python3 -m scripts.ops.coverage_live_proof run \
  --output /tmp/coverage-proof
```

`--dsn` may replace the environment variable. A missing DSN is refused. Known
production markers (`ec-prod`, `/opt/extra-consultoria`, `extra_prod`, …) are
refused. SQLite and MagicMock connections are refused.

## Flow

```
provision ephemeral database
        ↓
apply canonical migrations
  python3 -m scripts.ops.apply_migrations
        ↓
load deterministic seed (A / B / C)
        ↓
run shipped dual_coverage_evidence_gate
        ↓
run shipped golden path
  python3 -m scripts.golden_path --dsn … --execute-dual-coverage-only
        ↓
query + serialize evidence.json
        ↓
strip volatiles → evidence.normalized.json
        ↓
SHA-256 (semantic + files)
        ↓
DROP only coverage_live_proof_*
```

## Seed expectations

| Scenario | Seed | Expected |
|----------|------|----------|
| A source-wide only | aggregate row, NULL identity | `MISSING_EVIDENCE` / `source_wide_aggregate_without_identity`; entity numerator stays 0 |
| B mixed | same aggregate + one `ent-10` row | only the identified row enters the numerator; no double count |
| C incompatible | `identity_status=unmappable` | fail-closed `unmappable_evidence_cannot_drop` |
| D replay | apply the same seed twice | no extra rows; identical `normalized_semantic_hash` |

`GATE_THRESHOLD` is **read** from `scripts/coverage/dual_capability_coverage.py`
(currently 0.95). It is not redefined here.

## Evidence pack

`--output` receives:

- `evidence.json` — full run (includes `run_id`, duration, ephemeral name)
- `evidence.normalized.json` — volatiles stripped; byte-stable across replays
- `SHA256SUMS` — hashes of the two JSON files
- `coverage-live-proof.log` — sanitized (password/DSN redacted)
- `golden_path_ledger.json` — ledger from the shipped golden-path entry

## Tests

```bash
# orchestrator (no database)
python3 -m pytest tests/coverage_live_proof -o addopts='' -m 'not real_db'

# acceptance (real PostgreSQL)
REQUIRE_REAL_DB=1 LOCAL_DATALAKE_DSN='postgresql://test:test@127.0.0.1:5433/extra_test' \
  python3 -m pytest tests/coverage_live_proof -o addopts='' -m real_db

# existing #350 identity suite (unchanged)
python3 -m pytest tests/test_coverage_formula_and_identity.py -o addopts=''
```

## CI

Workflow: [`.github/workflows/coverage-live-proof.yml`](../../.github/workflows/coverage-live-proof.yml)

- required `workflow_dispatch`
- optional pull_request when this campaign’s files change
- `pgvector/pgvector:pg16` service, no external secrets
- `permissions: contents: read`
- uploads the evidence pack and sanitized logs
- teardown `if: always()`

Dispatch:

```bash
gh workflow run coverage-live-proof.yml --repo tjsasakifln/extra-cli
```

A green Actions run may be linked from the PR. Local real-PostgreSQL proof
alone is **not** `CI_PROVEN`.

## What this does not do

- Does not change `GATE_THRESHOLD` or any coverage formula
- Does not edit `scripts/golden_path.py`, `tests/conftest.py`, or `scripts/testing/**`
- Does not touch source registries, adapters, or PR #413
- Does not connect to `ec-prod` or `/opt/extra-consultoria`
- Does not treat leftover `extra_test` data as operational proof
