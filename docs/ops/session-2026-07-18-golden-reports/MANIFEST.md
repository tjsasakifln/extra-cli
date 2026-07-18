# Golden path reports + real PDF

Story ROI-cand-dyn-slice-4f08e0461629

## Commands
```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
python3 -m scripts.reports.golden_path_pack --dsn "$LOCAL_DATALAKE_DSN" --json
python3 scripts/reports/panorama.py --dsn "$LOCAL_DATALAKE_DSN" --output-pdf
pytest tests/test_golden_path_pack.py -q --no-cov
```

## Evidence
- pack/evidence-pack/*.csv (editais N=8, contratos N=0 honest empty, concorrentes, referencias)
- pack/evidence-pack/*.pdf size>0 (real reportlab)
- limitations documented in manifest
