# Quickstart — National Contracts Intelligence

## Prerequisites

```bash
cd /mnt/d/extra-consultoria-national-intelligence
export NATIONAL_INTEL_DSN="${NATIONAL_INTEL_DSN:-postgresql://test:test@127.0.0.1:5435/extra_national_intelligence_test}"
# NEVER default to 5433/extra_test while HC backfill runs
```

Isolated Postgres:

```bash
docker start extra-national-intel-db  # port 5435
```

## Apply migrations (isolated only)

```bash
python3 -m scripts.ops.apply_migrations --dsn "$NATIONAL_INTEL_DSN"
```

## Run products (after fixtures or data load)

```bash
python3 -m scripts.national_intel competitors \
  --dsn "$NATIONAL_INTEL_DSN" \
  --keyword "obra" \
  --limit 50 \
  --output artifacts/campaigns/NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01/products/competitors/example.json

python3 -m scripts.national_intel benchmarks \
  --dsn "$NATIONAL_INTEL_DSN" \
  --uf SC \
  --keyword "paviment" \
  --output artifacts/campaigns/NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01/products/benchmarks/example.json

python3 -m scripts.national_intel agencies \
  --dsn "$NATIONAL_INTEL_DSN" \
  --limit 50 \
  --output artifacts/campaigns/NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01/products/agencies/example.json
```

## Tests

```bash
export NATIONAL_INTEL_DSN=postgresql://test:test@127.0.0.1:5435/extra_national_intelligence_test
python3 -m pytest tests/national_intel/ -q --tb=short
```

## Expected outcomes

- JSON envelopes include `scope_label`, `limitations`, `row_count`
- Coverage isolation tests PASS (national volume ⟂ SC dual coverage)
- No process touches `hc_closure_3y` or PID of live backfill

## Related

- Spec: [spec.md](./spec.md)
- Data model: [data-model.md](./data-model.md)
- Isolation: [contracts/isolation-policy.md](./contracts/isolation-policy.md)
