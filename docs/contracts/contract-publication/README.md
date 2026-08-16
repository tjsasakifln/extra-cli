# Contract publication candidate engine

Producer for extra-cli#414. Reads a versioned snapshot + policy, ranks
candidates with `PUBLICATION_VALUE_SCORE`, writes immutable evidence packs
and a `public-read-contract-analysis/1.0` export for the #400 consumer.

This module does not publish pages, index, authorize `PUBLISHABLE_*` or
invent comparables.

## Commands

```bash
# Golden / labeled fixture
python3 -m scripts.contract_publication rank \
  --snapshot tests/fixtures/contract_publication/golden_corpus.json \
  --out artifacts/contract_publication/golden

# Rebuild one pack (determinism check)
python3 -m scripts.contract_publication rebuild-pack \
  --snapshot tests/fixtures/contract_publication/golden_corpus.json \
  --candidate-id CAND-BDI-01 \
  --out pack.json

# Consumer export expected by #400
python3 -m scripts.contract_publication export-400 \
  --snapshot tests/fixtures/contract_publication/golden_corpus.json \
  --out artifacts/contract_publication/export-400

# Official path — fail-closed when no versioned official projection exists
python3 -m scripts.contract_publication live --out artifacts/contract_publication/unavailable
```

`--policy` defaults to
`docs/contracts/contract-publication/publication-value-score-v1.json`.

## Output of `rank`

```
DIR/
  manifest.json
  candidates.json
  packs/<id>.json
  export-400/manifest.json
  export-400/analyses/<id>.json
  status-report.json
  status-report.md
```

`as_of` always comes from the snapshot. Wall-clock is forbidden.

## States

`REJECT | HOLD_FOR_DATA | EDITORIAL_REVIEW`

A fixture that claims official status is rejected (`fixture_as_live`).
The `--live` command emits `OFFICIAL_DATA_UNAVAILABLE` in the same schema
when no versioned official projection is authorized.

## Tests

```bash
python3 -m pytest tests/contract_publication -q --tb=short
```
