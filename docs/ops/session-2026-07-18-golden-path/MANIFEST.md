# Golden path §12.1 evidence

Story ROI-cand-dyn-slice-f7cf8ac7399c · cyc-2026-07-18T144628Z

## Canonical command
```bash
python3 -m scripts.golden_path
python3 -m scripts.golden_path --bootstrap --skip-crawl --skip-freshness --skip-reports --allow-zero
```

## Proven this slice
- Canonical CLI (`-m scripts.golden_path`)
- DB connectivity
- Migrations schema validation (idempotent)
- Universe seed import/validate + spreadsheet hash
- Ledger + logs + wall clock + git_sha + schema_version + limitations + reference period
- Fail-closed non-zero exit (unit tests)
- Re-run appends ledger (no crash)

## Not claimed as DONE without live data
- Full live crawl sources / persist product volume
- Coverage 95% / snapshot integrity commercial
- Full Excel/PDF commercial packs in this bootstrap-only mode (use full run without --skip-reports)
