# Golden path clean environment

Story ROI-cand-dyn-slice-16eac35a037b

## Command
```bash
python3 -m scripts.ops.golden_clean_env \
  --admin-dsn postgresql://test:test@127.0.0.1:5433/extra_test \
  --db-name extra_clean \
  --report docs/ops/session-2026-07-18-golden-clean/report.json
```

## Proof
- DROP/CREATE extra_clean (empty)
- migrations batch1 max=13 OK; later migrations applied (vector 014 skipped)
- public_tables=76
- golden_path --bootstrap --skip-crawl --skip-freshness --allow-zero exit 0
