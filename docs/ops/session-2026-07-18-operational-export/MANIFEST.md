# Evidence — §12.2 export + source health + metadata

**Story:** ROI-cand-dyn-slice-d58f00f868f0  
**Module:** `scripts/reports/operational_export_pack.py`

| Item | Proof |
|------|-------|
| source health | `pack/csv/source_health.csv` |
| Exportação CSV | `pack/csv/*.csv` + metadata.json |
| Exportação Excel | `pack/export-*.xlsx` size>0 |
| Relatório PDF | `pack/export-*.pdf` size>0 |
| data de geração | `generated_at` in manifest + excel metadata sheet |
| versão do universo | `universe_version` |
| fonte | `source` |
| status de confiabilidade | `reliability` |

## Commands
```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
python3 -m pytest tests/test_operational_export_pack.py -q --no-cov -o addopts=
python3 -m scripts.reports.operational_export_pack --dsn "$LOCAL_DATALAKE_DSN" --out docs/ops/session-2026-07-18-operational-export/pack --json
```
