# L1.5 — Golden path fetch → persistência → PDF/Excel

**Date:** 2026-07-16  
**Run ID:** `gp-20260716-200904`  
**Status:** **SUCCESS**

## Comando

```bash
export PYTHONPATH=.
export DATABASE_URL=postgresql://test:test@localhost:5433/pncp_datalake
python3 scripts/golden_path.py --sources pcp,compras_gov --skip-freshness
```

## Resultados

| Item | Valor |
|------|--------|
| Exit | 0 |
| pcp | OK fetched=181 |
| compras_gov | OK fetched=2 |
| Excel | `output/excels/panorama-SC-2026-07-16.xlsx` |
| PDF | generated (panorama pipeline) |
| Ledger | append OK (sem corrupção) |

## Fix incluso

- `monitor.py`: força project root no início de `sys.path` (evita shadow de `scripts/crawl/config.py`)
- `golden_path.py`: injeta `PYTHONPATH` nos subprocessos
